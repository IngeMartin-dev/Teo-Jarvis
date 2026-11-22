"""Control del PC (mouse y teclado), WhatsApp Desktop y Microsoft Store para Jarvis.

Permisos: todo viene activado. Para apagar algo, en config_local.py (o config.py) pon por ejemplo:
    PERMISOS = {"control_pc": False, "whatsapp": True, "tienda": True}

Seguridad integrada:
- Mover el mouse a la esquina superior izquierda de la pantalla detiene cualquier acción (failsafe).
- Jarvis NO actúa sobre terminales, el cuadro Ejecutar, el Registro, el Administrador de tareas ni avisos de UAC,
  ni escribe en ventanas de contraseñas o inicio de sesión.
- WhatsApp: escribe el mensaje, te deja revisarlo en pantalla y solo lo envía cuando tú dices que sí.
"""
import ctypes, os, re, shutil, subprocess, time
from ctypes import wintypes
from pathlib import Path
from urllib.parse import quote
import apps_index, config

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _permiso(nombre: str):
    """Devuelve None si está permitido, o un mensaje si el usuario lo desactivó."""
    if getattr(config, "PERMISOS", {}).get(nombre, True):
        return None
    return f"El permiso '{nombre}' está desactivado en la configuración (PERMISOS)."


# ============================== Microsoft Store (vía WinGet, fuente msstore) ==============================
def _winget():
    w = shutil.which("winget") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WindowsApps/winget.exe")
    return w if Path(w).exists() else None


def _limpiar(salida: str, ultimas: int = 20) -> str:
    lineas = []
    for l in salida.replace("\r", "\n").splitlines():
        l = l.rstrip()
        if not l.strip() or re.fullmatch(r"[\s\-\\|/]+", l) or "█" in l or "▒" in l:
            continue
        lineas.append(l)
    return "\n".join(lineas[-ultimas:])


def _args_instalar_tienda(nombre: str, id_producto: str = "") -> list:
    base = ["install"]
    if id_producto:
        base += ["--id", id_producto, "--exact"]
    else:
        base += ["--name", nombre, "--exact"]
    return base + ["--source", "msstore", "--accept-package-agreements", "--accept-source-agreements",
                   "--disable-interactivity"]


def abrir_tienda(consulta: str = "") -> str:
    """Abre Microsoft Store (en la búsqueda de la app si se indica)."""
    if (m := _permiso("tienda")):
        return m
    try:
        os.startfile("ms-windows-store://search/?query=" + quote(consulta) if consulta else "ms-windows-store://home")
        return f"Abrí Microsoft Store{(' buscando ' + consulta) if consulta else ''}."
    except Exception as e:
        return f"No pude abrir Microsoft Store: {e}"


def buscar_en_tienda(consulta: str) -> str:
    """Busca apps en Microsoft Store y devuelve nombre, id y versión."""
    if (m := _permiso("tienda")):
        return m
    consulta = consulta.strip()
    if not consulta or len(consulta) > 100:
        return "Dime qué app quieres buscar en Microsoft Store."
    w = _winget()
    if not w:
        return "No encuentro WinGet. Actualiza 'Instalador de aplicación' desde Microsoft Store."
    try:
        r = subprocess.run([w, "search", consulta, "--source", "msstore", "--accept-source-agreements"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60, creationflags=_SIN_VENTANA)
    except Exception as e:
        return f"No pude buscar en la Tienda: {e}"
    out = _limpiar(r.stdout)
    return out if r.returncode == 0 and out else f"No encontré '{consulta}' en Microsoft Store."


def instalar_desde_tienda(nombre: str, id_producto: str = "") -> str:
    """Instala una app de Microsoft Store por nombre exacto o por id de producto (12 caracteres, ej. 9NKSQGP7F2NH)."""
    if (m := _permiso("tienda")):
        return m
    nombre, id_producto = nombre.strip(), id_producto.strip()
    if id_producto and not re.fullmatch(r"[A-Za-z0-9]{12}", id_producto):
        return "El id de producto no es válido: debe tener 12 letras o números. Búscalo con buscar_en_tienda."
    if not id_producto and (not nombre or len(nombre) > 100 or any(ord(c) < 32 for c in nombre)):
        return "Dime el nombre exacto de la app de Microsoft Store."
    w = _winget()
    if not w:
        return "No encuentro WinGet. Actualiza 'Instalador de aplicación' desde Microsoft Store."
    try:
        r = subprocess.run([w] + _args_instalar_tienda(nombre, id_producto), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900, creationflags=_SIN_VENTANA)
    except subprocess.TimeoutExpired:
        return f"La instalación de {nombre or id_producto} superó el tiempo límite; revisa si Microsoft Store sigue descargando."
    except Exception as e:
        return f"No pude instalar {nombre or id_producto}: {e}"
    if r.returncode == 0:
        try:
            apps_index.cargar(forzar=True)
        except Exception:
            pass
        return f"Instalé {nombre or id_producto} desde Microsoft Store."
    return (f"No pude instalar {nombre or id_producto} desde Microsoft Store. Si hay varias coincidencias usa buscar_en_tienda "
            "y repite con el id de producto; si pide iniciar sesión, abre Microsoft Store e inicia sesión. "
            + _limpiar(r.stdout + "\n" + r.stderr, 6)[-300:])


# ============================== Mouse y teclado ==============================
_EXE_BLOQUEADOS = {"cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe", "conhost.exe",
                   "openconsole.exe", "wsl.exe", "bash.exe", "regedit.exe", "taskmgr.exe", "mmc.exe",
                   "consent.exe", "wscript.exe", "cscript.exe", "mshta.exe"}
_TITULOS_BLOQUEADOS = re.compile(
    r"\b(símbolo del sistema|simbolo del sistema|command prompt|powershell|terminal|editor del registro|registry editor|"
    r"administrador de tareas|task manager|control de cuentas|user account control|seguridad de windows)\b|^ejecutar$|^run$", re.I)
_TITULOS_CLAVE = re.compile(r"(contraseña|contrasena|password|iniciar sesión|iniciar sesion|sign in|log in|login|"
                            r"credencial|pin de windows)", re.I)
_COMBOS_BLOQUEADOS = [{"win", "r"}, {"win", "x"}, {"ctrl", "shift", "esc"}, {"ctrl", "alt", "delete"}, {"ctrl", "alt", "del"}]


def _ventana() -> tuple:
    """(título, ejecutable) de la ventana activa; vacíos si no se puede leer."""
    try:
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        h = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        exe = ""
        hp = k.OpenProcess(0x1000, False, pid.value)
        if hp:
            b2, sz = ctypes.create_unicode_buffer(520), wintypes.DWORD(520)
            if k.QueryFullProcessImageNameW(hp, 0, b2, ctypes.byref(sz)):
                exe = Path(b2.value).name.lower()
            k.CloseHandle(hp)
        return buf.value, exe
    except Exception:
        return "", ""


def _bloqueo(titulo: str, exe: str, escribiendo: bool = False):
    """Mensaje si la ventana está prohibida para Jarvis, o None."""
    if exe in _EXE_BLOQUEADOS or _TITULOS_BLOQUEADOS.search(titulo):
        return f"Por seguridad no actúo sobre esta ventana ({titulo or exe})."
    if escribiendo and _TITULOS_CLAVE.search(titulo):
        return "Por seguridad no escribo en ventanas de contraseña o inicio de sesión; hazlo tú."
    return None


def _combo_bloqueado(teclas: list) -> bool:
    s = {t.lower() for t in teclas}
    return any(c <= s for c in _COMBOS_BLOQUEADOS)


def _pg():
    import pyautogui
    pyautogui.FAILSAFE = True   # mouse a la esquina superior izquierda = parar
    pyautogui.PAUSE = 0.25
    return pyautogui


def _pegar(texto: str):
    """Escribe texto (con tildes y emojis) usando el portapapeles y lo restaura después."""
    import pyperclip
    pg = _pg()
    try:
        previo = pyperclip.paste()
    except Exception:
        previo = None
    pyperclip.copy(texto)
    pg.hotkey("ctrl", "v")
    time.sleep(0.3)
    if previo is not None:
        try:
            pyperclip.copy(previo)
        except Exception:
            pass


def _control(escribiendo: bool = False):
    """Revisa permiso y ventana activa. Devuelve mensaje de error o None."""
    if (m := _permiso("control_pc")):
        return m
    return _bloqueo(*_ventana(), escribiendo=escribiendo)


def tamano_pantalla() -> str:
    try:
        pg = _pg()
        w, h = pg.size()
        x, y = pg.position()
        t, exe = _ventana()
        return f"Pantalla {w}x{h} píxeles. Mouse en ({x}, {y}). Ventana activa: {t or exe or 'desconocida'}."
    except Exception as e:
        return f"No pude leer la pantalla: {e}"


def mover_mouse(x: int, y: int) -> str:
    if (m := _control()):
        return m
    try:
        pg = _pg()
        w, h = pg.size()
        if not (0 < int(x) < w - 1 and 0 < int(y) < h - 1):
            return f"Esas coordenadas están fuera de la pantalla ({w}x{h})."
        pg.moveTo(int(x), int(y), duration=0.3)
        return f"Moví el mouse a ({int(x)}, {int(y)})."
    except Exception as e:
        return f"No pude mover el mouse: {e}"


def clic(x: int, y: int, boton: str = "left", doble: bool = False) -> str:
    if (m := _control()):
        return m
    try:
        pg = _pg()
        w, h = pg.size()
        if not (0 < int(x) < w - 1 and 0 < int(y) < h - 1):
            return f"Esas coordenadas están fuera de la pantalla ({w}x{h})."
        boton = "right" if boton in ("right", "derecho", "derecha") else "left"
        pg.moveTo(int(x), int(y), duration=0.3)
        pg.click(button=boton, clicks=2 if doble else 1)
        return f"Hice clic{' doble' if doble else ''} en ({int(x)}, {int(y)})."
    except Exception as e:
        return f"No pude hacer clic: {e}"


def scroll(cantidad: int) -> str:
    if (m := _control()):
        return m
    try:
        _pg().scroll(max(-2000, min(2000, int(cantidad))))
        return "Listo, hice scroll."
    except Exception as e:
        return f"No pude hacer scroll: {e}"


def escribir_texto(texto: str, enter: bool = False) -> str:
    """Escribe texto donde esté el cursor en la ventana activa (máx. 500 caracteres)."""
    if (m := _control(escribiendo=True)):
        return m
    if not texto or len(texto) > 500:
        return "El texto está vacío o es demasiado largo (máximo 500 caracteres)."
    try:
        _pegar(texto)
        if enter:
            _pg().press("enter")
        return "Escribí el texto." + (" Presioné Enter." if enter else "")
    except Exception as e:
        return f"No pude escribir: {e}"


def presionar_teclas(teclas: str) -> str:
    """Presiona una tecla o combinación, ej. 'enter', 'ctrl+c', 'alt+tab', 'win+d'."""
    if (m := _control()):
        return m
    partes = [{"windows": "win", "control": "ctrl", "escape": "esc", "suprimir": "delete", "borrar": "backspace"}
              .get(p.strip().lower(), p.strip().lower()) for p in teclas.split("+") if p.strip()]
    if not partes or len(partes) > 4:
        return "Indica una tecla o una combinación de hasta 4 teclas, por ejemplo ctrl+c."
    if _combo_bloqueado(partes):
        return "Esa combinación de teclas está bloqueada por seguridad."
    try:
        pg = _pg()
        invalidas = [p for p in partes if p not in pg.KEYBOARD_KEYS]
        if invalidas:
            return f"No reconozco la tecla: {', '.join(invalidas)}."
        pg.hotkey(*partes) if len(partes) > 1 else pg.press(partes[0])
        return f"Presioné {'+'.join(partes)}."
    except Exception as e:
        return f"No pude presionar las teclas: {e}"


# ---- Controles por nombre (UI Automation): más fiable que adivinar coordenadas ----
_TIPOS_UIA = ("Button", "MenuItem", "ListItem", "Hyperlink", "TabItem", "CheckBox", "RadioButton",
              "ComboBox", "SplitButton", "Edit")


def _elementos(limite: int = 60):
    from pywinauto import Desktop
    h = ctypes.windll.user32.GetForegroundWindow()
    win = Desktop(backend="uia").window(handle=h)
    fin, res = time.time() + 8, []
    for tipo in _TIPOS_UIA:
        try:
            for e in win.descendants(control_type=tipo):
                nombre = (e.window_text() or "").strip()
                if nombre and len(nombre) < 80 and e.is_visible():
                    res.append((tipo, nombre, e))
                if len(res) >= limite or time.time() > fin:
                    return res
        except Exception:
            continue
    return res


def listar_elementos() -> str:
    """Lista botones, menús y campos con nombre de la ventana activa, para poder usar clic_elemento."""
    if (m := _control()):
        return m
    try:
        els = _elementos()
        if not els:
            return "No encontré controles con nombre en la ventana activa."
        t, _ = _ventana()
        return f"Ventana: {t}\n" + "\n".join(f"{tipo}: {nombre}" for tipo, nombre, _e in els)
    except ImportError:
        return "Falta pywinauto. Ejecuta: python -m pip install -r requirements.txt"
    except Exception as e:
        return f"No pude leer los controles de la ventana: {e}"


def clic_elemento(nombre: str) -> str:
    """Hace clic en el botón, menú, enlace o pestaña que tenga ese nombre en la ventana activa."""
    if (m := _control()):
        return m
    q = nombre.strip().casefold()
    if not q:
        return "Dime el nombre del botón o elemento."
    try:
        els = _elementos(150)
        el = next((e for _t, n, e in els if n.casefold() == q), None) or \
             next((e for _t, n, e in els if q in n.casefold()), None)
        if el is None:
            return f"No encontré '{nombre}' en la ventana activa. Usa listar_elementos para ver qué hay."
        el.click_input()
        return f"Hice clic en «{nombre}»."
    except ImportError:
        return "Falta pywinauto. Ejecuta: python -m pip install -r requirements.txt"
    except Exception as e:
        return f"No pude hacer clic en '{nombre}': {e}"


# ============================== WhatsApp Desktop ==============================
_wa: dict = {}
_WA_VIGENCIA = 300  # segundos que vale un mensaje preparado


def _telefono(destino: str):
    """Número con indicativo de país (solo dígitos) o None si es un nombre. 10 dígitos que empiezan por 3 = Colombia (57)."""
    d = re.sub(r"[\s\-().]", "", destino.strip())
    if not re.fullmatch(r"\+?\d{8,15}", d):
        return None
    d = d.lstrip("+")
    return "57" + d if len(d) == 10 and d.startswith("3") else d


def _whatsapp_al_frente(segundos: float = 12) -> bool:
    fin = time.time() + segundos
    while time.time() < fin:
        t, exe = _ventana()
        if "whatsapp" in t.lower() or "whatsapp" in exe:
            return True
        time.sleep(0.5)
    return False


def enviar_whatsapp(destino: str, mensaje: str) -> str:
    """Prepara un mensaje de WhatsApp (NO lo envía). destino = nombre del contacto o número con indicativo."""
    if (m := _permiso("whatsapp") or _permiso("control_pc")):
        return m
    destino, mensaje = destino.strip(), mensaje.strip()
    if not destino or len(destino) > 60 or not mensaje or len(mensaje) > 1000:
        return "Necesito un contacto (o número) y un mensaje de máximo 1000 caracteres."
    _wa.clear()
    try:
        tel = _telefono(destino)
        os.startfile(f"whatsapp://send?phone={tel}&text={quote(mensaje)}" if tel else "whatsapp:")
        if not _whatsapp_al_frente():
            return "No pude abrir WhatsApp Desktop o no se puso al frente. ¿Está instalado y con la sesión iniciada?"
        time.sleep(2.5)
        if not tel:  # por nombre: buscar el chat con Ctrl+F, abrir el primer resultado y pegar el mensaje
            pg = _pg()
            pg.hotkey("ctrl", "f"); time.sleep(0.6)
            _pegar(destino); time.sleep(1.6)
            pg.press("enter"); time.sleep(1.4)
            _pegar(mensaje)
        if not _whatsapp_al_frente(3):
            return "WhatsApp dejó de estar al frente; no preparé nada."
        _wa.update(destino=destino, mensaje=mensaje, ts=time.time())
        return (f"Dejé escrito el mensaje para «{destino}» en WhatsApp, pero NO lo envié. Dile al usuario que revise en "
                "pantalla que sea el chat correcto y pregúntale si lo envías.")
    except Exception as e:
        return f"No pude preparar el mensaje: {e}"


def confirmar_whatsapp() -> str:
    """Envía el mensaje preparado. Solo después de que el usuario diga que sí."""
    if (m := _permiso("whatsapp") or _permiso("control_pc")):
        return m
    if not _wa or time.time() - _wa.get("ts", 0) > _WA_VIGENCIA:
        _wa.clear()
        return "No hay ningún mensaje de WhatsApp preparado (o ya venció). Pídemelo de nuevo."
    t, exe = _ventana()
    if "whatsapp" not in t.lower() and "whatsapp" not in exe:
        _wa.clear()
        return "WhatsApp ya no está al frente, así que no envié nada. Pídeme el mensaje otra vez."
    try:
        _pg().press("enter")
        destino = _wa.get("destino", "")
        _wa.clear()
        return f"Mensaje enviado a {destino}."
    except Exception as e:
        return f"No pude enviar el mensaje: {e}"


def cancelar_whatsapp() -> str:
    pendiente = bool(_wa)
    _wa.clear()
    t, exe = _ventana()
    if pendiente and ("whatsapp" in t.lower() or "whatsapp" in exe):
        try:
            pg = _pg()
            pg.hotkey("ctrl", "a"); pg.press("backspace")
        except Exception:
            pass
    return "Descarté el mensaje de WhatsApp."


# ============================== Registro para el LLM ==============================
def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


S, I, B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
SPEC = [
    _t("abrir_tienda", "Abre Microsoft Store, opcionalmente buscando una app", {"consulta": S}, []),
    _t("buscar_en_tienda", "Busca apps en Microsoft Store y devuelve nombre, id y versión", {"consulta": S}, ["consulta"]),
    _t("instalar_desde_tienda", "Instala una app de Microsoft Store que el usuario pidió explícitamente, por nombre exacto o id de producto",
       {"nombre": S, "id_producto": S}, ["nombre"]),
    _t("tamano_pantalla", "Devuelve el tamaño de la pantalla, la posición del mouse y la ventana activa", {}, []),
    _t("listar_elementos", "Lista los botones, menús y campos con nombre de la ventana activa", {}, []),
    _t("clic_elemento", "Hace clic en un botón, menú, enlace o pestaña de la ventana activa por su nombre (preferido sobre clic con coordenadas)",
       {"nombre": S}, ["nombre"]),
    _t("mover_mouse", "Mueve el mouse a coordenadas en píxeles de la pantalla", {"x": I, "y": I}, ["x", "y"]),
    _t("clic", "Hace clic con el mouse en coordenadas en píxeles de la pantalla",
       {"x": I, "y": I, "boton": {"type": "string", "enum": ["left", "right"]}, "doble": B}, ["x", "y"]),
    _t("scroll", "Hace scroll con la rueda del mouse (positivo = arriba, negativo = abajo)", {"cantidad": I}, ["cantidad"]),
    _t("escribir_texto", "Escribe texto con el teclado en la ventana activa", {"texto": S, "enter": B}, ["texto"]),
    _t("presionar_teclas", "Presiona una tecla o combinación, por ejemplo enter, ctrl+c, alt+tab", {"teclas": S}, ["teclas"]),
    _t("enviar_whatsapp", "Prepara un mensaje en WhatsApp Desktop (NO lo envía). destino = nombre del contacto o número con indicativo. "
                          "Después pregunta al usuario si lo envías",
       {"destino": S, "mensaje": S}, ["destino", "mensaje"]),
    _t("confirmar_whatsapp", "Envía el mensaje de WhatsApp preparado. Solo después de que el usuario diga que sí", {}, []),
    _t("cancelar_whatsapp", "Descarta el mensaje de WhatsApp preparado", {}, []),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in SPEC}
