"""Ventana de llamada de WhatsApp Desktop (solo Windows): detectar, aceptar, rechazar y colgar.

Usa UI Automation (pywinauto) y busca los botones por su NOMBRE (config.LLAMADA_BTN_*), no por coordenadas.

Por qué está hecho así (WhatsApp Desktop es una app WebView2/Chromium, y leer su árbol de accesibilidad es LENTO, a veces
decenas de segundos la primera vez):
- Detectar que hay una ventana candidata es instantáneo (EnumWindows, sin UI Automation). Si no hay ninguna, no se lee nada.
- Todo lo de UI Automation corre en UN hilo dedicado, con límite de tiempo (LLAMADA_UIA_TIMEOUT). Si Windows se atasca, nadie
  más (ni la voz ni el vigilante) se queda esperando.
- El resultado de cada lectura se guarda en caché unos segundos, y los botones encontrados se reutilizan para aceptar.
- Cada lectura queda anotada en el registro (~/.jarvis/llamadas.log) con lo que tardó.

Cada función devuelve datos simples para que llamadas.py (la lógica) se pueda probar sin Windows.
"""
import ctypes, queue, re, threading, time
from ctypes import wintypes
from pathlib import Path
import config, registro

_GENERICOS = re.compile(r"whatsapp|llamada|call|voz|voice|video|entrante|incoming|llamando|calling|ringing|timbrando|"
                        r"aceptar|rechazar|accept|decline|encrypt|cifrad|cámara|camera|micr[oó]fono|microphone|audio|settings|chat", re.I)
_TIPOS_BOTON = ("Button", "Hyperlink", "Custom", "Group")   # WebView2 no siempre expone los botones como «Button»
_TTL = 6.0          # segundos que vale una lectura en caché
_ABANDONO = 45.0    # si una tarea de UI Automation lleva tanto atascada, se descarta el hilo y se crea otro


def _rx(nombre: str) -> "re.Pattern":
    return re.compile(getattr(config, nombre), re.I)


def _timeout() -> float:
    try:
        return max(2.0, float(getattr(config, "LLAMADA_UIA_TIMEOUT", 20)))
    except (TypeError, ValueError):
        return 20.0


# ---------------- Hilo dedicado a UI Automation ----------------
class _HiloUIA:
    def __init__(self):
        self.cola = queue.Queue()
        self.ocupado_desde = None
        threading.Thread(target=self._bucle, daemon=True, name="uia-llamadas").start()

    def atascado(self) -> bool:
        return self.ocupado_desde is not None and time.time() - self.ocupado_desde > _ABANDONO

    def _bucle(self):
        try:   # pywinauto/comtypes necesitan COM inicializado en el hilo que los usa
            import comtypes
            comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)
        except Exception:
            pass
        while True:
            fn, res, ev = self.cola.get()
            if res.get("cancelado"):          # quien la pidió ya se rindió: no la ejecutes tarde (podría hacer un clic viejo)
                ev.set()
                continue
            self.ocupado_desde = time.time()
            try:
                res["v"] = fn()
            except BaseException as e:        # noqa: BLE001 - se devuelve al que esperaba
                res["e"] = e
            self.ocupado_desde = None
            ev.set()


_hilo = None
_hilo_lock = threading.Lock()


def en_hilo(fn, timeout: float):
    """Ejecuta fn() en el hilo de UI Automation. Lanza TimeoutError si no termina en `timeout` segundos (la tarea queda
    cancelada si todavía no había empezado)."""
    global _hilo
    with _hilo_lock:
        if _hilo is None or _hilo.atascado():
            _hilo = _HiloUIA()
        h = _hilo
    res, ev = {}, threading.Event()
    h.cola.put((fn, res, ev))
    if not ev.wait(timeout):
        res["cancelado"] = True
        raise TimeoutError(f"UI Automation no respondió en {timeout:g} s")
    if "e" in res:
        raise res["e"]
    return res.get("v")


# ---------------- Ventanas (rápido, sin UI Automation) ----------------
def _exe(pid: int) -> str:
    try:
        k = ctypes.windll.kernel32
        hp = k.OpenProcess(0x1000, False, pid)
        if not hp:
            return ""
        try:
            buf, tam = ctypes.create_unicode_buffer(520), wintypes.DWORD(520)
            return Path(buf.value).name.lower() if k.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(tam)) else ""
        finally:
            k.CloseHandle(hp)
    except Exception:
        return ""


def ventanas_whatsapp(solo: bool = True) -> list:
    """Ventanas visibles de nivel superior de WhatsApp (o todas con solo=False): [{hwnd, titulo, exe, w, h, left, top}]."""
    u = ctypes.WinDLL("user32")  # instancia propia: no toca los prototipos que usa el resto de Jarvis
    u.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    res = []

    def cb(hwnd, _lp):
        try:
            if not u.IsWindowVisible(hwnd):
                return True
            n = u.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            exe = _exe(pid.value)
            if not solo or "whatsapp" in exe or "whatsapp" in buf.value.lower():
                r = wintypes.RECT()
                u.GetWindowRect(hwnd, ctypes.byref(r))
                res.append({"hwnd": hwnd, "titulo": buf.value, "exe": exe, "w": r.right - r.left, "h": r.bottom - r.top,
                            "left": r.left, "top": r.top})
        except Exception:
            pass
        return True

    u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return res


def _candidatas() -> list:
    """Ventanas de WhatsApp que pueden ser una llamada: pequeñas (aviso o ventana de llamada) o con «llamada» en el título.
    Así no se recorre el árbol enorme de la ventana principal."""
    max_w, max_h = getattr(config, "LLAMADA_VENTANA_MAX", (700, 500))
    return [v for v in ventanas_whatsapp()
            if (0 < v["w"] <= max_w or 0 < v["h"] <= max_h) or re.search(r"llamada|call", v["titulo"], re.I)]


def _visible(hwnd) -> bool:
    try:
        u = ctypes.WinDLL("user32")
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        return bool(u.IsWindowVisible(hwnd))
    except Exception:
        return False


# ---------------- Lectura con UI Automation (solo dentro del hilo UIA) ----------------
_cache: dict = {}   # hwnd -> {"t": hora, "info": dict | None}
_els: dict = {}     # hwnd -> {"aceptar": elemento, "rechazar": elemento, "colgar": elemento}


def _controles(hwnd, tipo: str) -> list:
    from pywinauto import Desktop
    win = Desktop(backend="uia").window(handle=hwnd)
    res = []
    for e in win.descendants(control_type=tipo):
        try:
            nombre = (e.window_text() or "").strip()
        except Exception:
            continue
        if nombre:
            res.append((nombre, e))
    return res


_ultimo_nombre: dict = {}


def _titulo_activa(v: dict) -> bool:
    """True si el título de la ventana es el de una llamada en curso (LLAMADA_TITULO_ACTIVA)."""
    try:
        return bool(re.search(getattr(config, "LLAMADA_TITULO_ACTIVA",
                                      r"voice call|video call|llamada de voz|videollamada|^\s*llamada\b|^\s*call\b"),
                              v.get("titulo", ""), re.I))
    except re.error:
        return False


def centro_llamada():
    """(x, y, ancho, alto) de la ventana de llamada en curso (o None), para buscar su botón de colgar mirando la pantalla."""
    try:
        for v in ventanas_whatsapp():
            if _titulo_activa(v) and v["w"] > 0 and v["h"] > 0:
                return v["left"], v["top"], v["w"], v["h"]
    except Exception:
        pass
    return None


def _nombre_llamante(textos: list) -> str:
    for t in textos:
        t = re.sub(r"[\ue000-\uf8ff]", "", t).strip()   # iconos de la fuente de WhatsApp
        if 1 < len(t) <= 60 and not _GENERICOS.search(t):
            return t
    return ""


def _analizar(v: dict):
    """Lee la ventana v y devuelve {'tipo': 'entrante'|'activa', ...} o None. Guarda caché y botones."""
    t0, hwnd = time.time(), v["hwnd"]
    claves = (("aceptar", _rx("LLAMADA_BTN_ACEPTAR")), ("rechazar", _rx("LLAMADA_BTN_RECHAZAR")),
              ("colgar", _rx("LLAMADA_BTN_COLGAR")))
    els, nombres = {}, []
    for tipo in _TIPOS_BOTON:
        for n, e in _controles(hwnd, tipo):
            nombres.append(n)
            for clave, rx in claves:
                if clave not in els and rx.search(n):
                    els[clave] = e
        if "aceptar" in els or "colgar" in els:
            break
    info = None
    if "aceptar" not in els and "colgar" not in els and _titulo_activa(v):
        # La ventana de llamada en curso (p. ej. «Voice call») solo expone minimizar/maximizar/cerrar: no tiene botones
        # legibles, pero su título delata que hay una llamada. Se mantiene el nombre visto durante el timbre.
        info = {"tipo": "activa", "hwnd": hwnd, "nombre": _ultimo_nombre.get("n", ""),
                "video": bool(re.search(r"video", v["titulo"], re.I)), "solo_titulo": True}
    elif "aceptar" in els or "colgar" in els:
        textos = [n for n, _e in _controles(hwnd, "Text")]
        todo = " ".join(textos + nombres + [v["titulo"]])
        info = {"tipo": "entrante" if "aceptar" in els else "activa", "hwnd": hwnd,
                "nombre": _nombre_llamante(textos), "video": bool(re.search(r"video", todo, re.I))}
        _els[hwnd] = els
        if info["nombre"]:
            _ultimo_nombre["n"] = info["nombre"]
    _cache[hwnd] = {"t": time.time(), "info": info}
    registro.escribir(f"leí la ventana {v['titulo']!r} [{v['exe']}] {v['w']}x{v['h']} en {time.time() - t0:.1f}s -> "
                      f"{info} | controles: {nombres[:10]}")
    return info


def buscar_llamada():
    """None si no hay llamada, o {'tipo': 'entrante'|'activa', 'nombre', 'video', 'hwnd'}.
    Puede lanzar TimeoutError si UI Automation tarda más de LLAMADA_UIA_TIMEOUT (la lectura sigue en segundo plano y la
    siguiente consulta usa su resultado en caché)."""
    cands = _candidatas()
    if not cands:                      # caso normal: no hay ventana de llamada, no se lee nada
        _cache.clear()
        _els.clear()
        return None
    visibles = {v["hwnd"] for v in cands}
    for k in list(_cache):
        if k not in visibles:
            _cache.pop(k, None)
            _els.pop(k, None)
    for v in cands[:3]:
        c = _cache.get(v["hwnd"])
        if c is not None and time.time() - c["t"] < _TTL:
            info = c["info"]
        else:
            info = en_hilo(lambda v=v: _analizar(v), _timeout())
        if info:
            return info
    return None


def _accionar(e):
    try:
        e.invoke()
    except Exception:
        e.click_input()


def _pulsar(patron: str, clave: str) -> bool:
    def tarea():
        for hwnd, els in list(_els.items()):         # botones ya encontrados: no hace falta volver a leer
            e = els.get(clave)
            if e is not None and _visible(hwnd):
                try:
                    _accionar(e)
                    registro.escribir(f"pulsé «{clave}» (botón en caché)")
                    return True
                except Exception as ex:
                    registro.escribir(f"falló «{clave}» en caché: {type(ex).__name__}: {ex}")
        rx = _rx(patron)
        for v in _candidatas():
            for tipo in _TIPOS_BOTON:
                for nombre, e in _controles(v["hwnd"], tipo):
                    if rx.search(nombre):
                        _accionar(e)
                        registro.escribir(f"pulsé «{clave}» ({nombre!r}) tras leer la ventana")
                        return True
        return False
    return bool(en_hilo(tarea, _timeout()))


def aceptar() -> bool:
    return _pulsar("LLAMADA_BTN_ACEPTAR", "aceptar")


def rechazar() -> bool:
    return _pulsar("LLAMADA_BTN_RECHAZAR", "rechazar")


def colgar() -> bool:
    return _pulsar("LLAMADA_BTN_COLGAR", "colgar")


# ---------------- Diagnóstico ----------------
_SHELL = {"shellexperiencehost.exe", "applicationframehost.exe", "startmenuexperiencehost.exe", "searchhost.exe"}


def _resumen_controles(hwnd) -> list:
    """Nombres de los controles de una ventana, por tipo (se ejecuta en el hilo UIA)."""
    lineas = []
    for tipo in _TIPOS_BOTON + ("Text",):
        try:
            nombres = [n for n, _e in _controles(hwnd, tipo)][:12]
        except Exception as e:
            nombres = [f"(error {type(e).__name__})"]
        if nombres:
            lineas.append(f"    {tipo}: " + " | ".join(nombres))
    return lineas or ["    (sin controles con nombre)"]


def instantanea() -> list:
    """Líneas que describen lo que hay en pantalla ahora, para el diagnóstico de llamadas. Por privacidad solo muestra el
    TÍTULO de las ventanas de WhatsApp, las pequeñas (avisos y ventanas emergentes) y las del shell de Windows (avisos);
    de las demás solo el programa. Nunca se bloquea: cada lectura de controles tiene límite de tiempo."""
    lineas = []
    try:
        todas = ventanas_whatsapp(solo=False)
    except Exception as e:
        return [f"No pude listar las ventanas: {e}"]
    for v in todas:
        if v["w"] <= 0 or v["h"] <= 0:
            continue
        pequena = v["w"] <= 700 or v["h"] <= 500
        wa = "whatsapp" in v["exe"] or "whatsapp" in v["titulo"].lower()
        if wa or pequena or v["exe"] in _SHELL:
            if not (v["titulo"] or wa or v["exe"] in _SHELL):
                continue
            lineas.append(f"[{v['exe'] or '?'}] «{v['titulo']}» {v['w']}x{v['h']}")
            if wa and (pequena or re.search(r"llamada|call", v["titulo"], re.I)):
                t0 = time.time()
                try:
                    lineas += en_hilo(lambda h=v["hwnd"]: _resumen_controles(h), _timeout())
                    registro.escribir(f"diagnóstico: controles de {v['titulo']!r} leídos en {time.time() - t0:.1f}s")
                except TimeoutError as e:
                    lineas.append(f"    lectura de controles: {e}")
                except Exception as e:
                    lineas.append(f"    no pude leer sus controles: {type(e).__name__}: {e}")
        else:
            lineas.append(f"[{v['exe'] or '?'}] (ventana grande, título oculto) {v['w']}x{v['h']}")
    return lineas


def diagnostico() -> str:
    """Qué ve Jarvis ahora mismo (una sola lectura)."""
    return "\n".join(instantanea())[:1800]
