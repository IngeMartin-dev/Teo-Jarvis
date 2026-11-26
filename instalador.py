"""Instalar programas: primero Microsoft Store; si no está ahí, busca una versión segura en WinGet y te PREGUNTA.

Flujo de instalar(nombre):
  1. Busca en Microsoft Store (winget, fuente msstore). Si hay una coincidencia clara, la instala sin preguntar: tú lo pediste.
  2. Si no está en la Tienda, busca en el catálogo de WinGet (fuente winget): sus paquetes se revisan antes de publicarse y
     el instalador se verifica con un hash. Jarvis NO instala nada todavía: te dice qué encontró y espera tu «sí»
     (confirmar_instalacion) o tu «no» (cancelar_instalacion).
  3. Si no está en ninguno, te lo dice. Jarvis nunca descarga instaladores de páginas web por su cuenta.
Todo se instala solo para tu usuario, sin pedir permisos de administrador (si el paquete los exige, se rechaza).
"""
import re, subprocess, time
import apps_index, config, tools_pc

_pendiente: dict = {}
_VIGENCIA = 300  # segundos que vale una propuesta de instalación
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ID_STORE = re.compile(r"[A-Za-z0-9]{12}")
_ID_WINGET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{1,100}")


def _ejecutar(args: list, timeout: int = 60) -> str:
    r = subprocess.run([tools_pc._winget()] + args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=_SIN_VENTANA)
    return (r.stdout or "") + "\n" + (r.stderr or "")


def parsear_busqueda(salida: str, fuente: str) -> list:
    """Filas de la tabla de `winget search`: [{nombre, id, version, fuente}]. No depende del idioma de Windows:
    toma lo que viene después de la línea de guiones y separa las columnas por 2 o más espacios."""
    filas, tabla = [], False
    for linea in salida.replace("\r", "\n").splitlines():
        if re.fullmatch(r"-{5,}", linea.strip()):
            tabla = True
            continue
        if not tabla or not linea.strip():
            continue
        cols = re.split(r"\s{2,}", linea.strip())
        if len(cols) >= 2:
            filas.append({"nombre": cols[0], "id": cols[1], "version": cols[2] if len(cols) > 2 else "", "fuente": fuente})
    return filas


def _buscar(consulta: str, fuente: str) -> list:
    salida = _ejecutar(["search", consulta, "--source", fuente, "--accept-source-agreements", "--disable-interactivity"])
    return parsear_busqueda(salida, fuente)


def puntaje(consulta: str, nombre: str) -> int:
    """3 = mismo nombre; 2 = empieza por la consulta (p. ej. «Spotify - Music»); 1 = contiene todas sus palabras; 0 = no."""
    q, n = apps_index._norm(consulta), apps_index._norm(nombre)
    if not q or not n:
        return 0
    if n == q:
        return 3
    if n.startswith(q + " "):
        return 2
    return 1 if set(q.split()) <= set(n.split()) else 0


def elegir(consulta: str, filas: list, id_valido, minimo: int = 2):
    """(candidata, alternativas). candidata solo si hay UNA mejor clara (puntaje >= minimo y sin empate); si no, None y
    las alternativas para que el usuario escoja. Para instalar sin preguntar (Tienda) se exige 2; con WinGet, que siempre
    pide confirmación, basta 1."""
    con_puntaje = [(puntaje(consulta, f["nombre"]), f) for f in filas if id_valido.fullmatch(f["id"])]
    con_puntaje = [(p, f) for p, f in con_puntaje if p >= 1]
    if not con_puntaje:
        return None, []
    con_puntaje.sort(key=lambda x: -x[0])
    mejor = con_puntaje[0][0]
    empatadas = [f for p, f in con_puntaje if p == mejor]
    if mejor >= minimo and len(empatadas) == 1:
        return empatadas[0], []
    return None, [f for _p, f in con_puntaje[:4]]


def _editor(fila: dict) -> str:
    """Editor tal como lo muestra el id de WinGet (Editor.Paquete). Solo es una pista; no se afirma nada más."""
    return fila["id"].split(".")[0] if "." in fila["id"] else ""


def instalar(nombre: str) -> str:
    """Punto de entrada para el LLM: Tienda primero, WinGet con confirmación después."""
    if (m := tools_pc._permiso("tienda")):
        return m
    nombre = (nombre or "").strip()
    if not nombre or len(nombre) > 100 or nombre.startswith("-") or any(ord(c) < 32 for c in nombre):
        return "Dime el nombre de la aplicación que quieres instalar."
    if not tools_pc._winget():
        return "No encuentro WinGet. Instala o actualiza 'Instalador de aplicación' desde Microsoft Store."
    _pendiente.clear()
    try:
        tienda = _buscar(nombre, "msstore")
    except Exception as e:
        return f"No pude buscar en Microsoft Store: {e}"
    elegida, alternativas = elegir(nombre, tienda, _ID_STORE)
    if elegida:
        return tools_pc.instalar_desde_tienda(elegida["nombre"], elegida["id"])
    if alternativas:
        opciones = "; ".join(f"{a['nombre']} (id {a['id']})" for a in alternativas)
        return (f"En Microsoft Store hay varias que se parecen a «{nombre}»: {opciones}. No instalé nada. "
                "Pregúntale al usuario cuál quiere y usa instalar_desde_tienda con ese nombre exacto y su id_producto.")
    try:
        catalogo = _buscar(nombre, "winget")
    except Exception as e:
        return f"No está en Microsoft Store y no pude buscar en WinGet: {e}"
    elegida, alternativas = elegir(nombre, catalogo, _ID_WINGET, minimo=1)
    if elegida:
        _pendiente.update(id=elegida["id"], nombre=elegida["nombre"], ts=time.time())
        editor = _editor(elegida)
        return (f"No está en Microsoft Store, pero encontré «{elegida['nombre']}»"
                f"{' del editor ' + editor if editor else ''} (id {elegida['id']}"
                f"{', versión ' + elegida['version'] if elegida['version'] else ''}) en el catálogo de WinGet, "
                "donde los instaladores se verifican. NO instalé nada todavía. Pregúntale al usuario si la instalas "
                "y usa confirmar_instalacion solo si dice que sí (o cancelar_instalacion si dice que no).")
    if alternativas:
        opciones = "; ".join(f"{a['nombre']} (id {a['id']})" for a in alternativas)
        return (f"No está en Microsoft Store y en WinGet hay varias parecidas a «{nombre}»: {opciones}. No instalé nada. "
                "Pregúntale al usuario cuál quiere; con su respuesta vuelve a llamar a instalar_app con el nombre exacto.")
    return (f"No encontré «{nombre}» ni en Microsoft Store ni en el catálogo verificado de WinGet. No descargo instaladores "
            "de páginas web por mi cuenta. Si quieres, puedo abrir el navegador para que busques su sitio oficial.")


def confirmar_instalacion() -> str:
    """Instala el paquete de WinGet propuesto. Solo después de que el usuario diga que sí."""
    if (m := tools_pc._permiso("tienda")):
        return m
    if not _pendiente or time.time() - _pendiente.get("ts", 0) > _VIGENCIA:
        _pendiente.clear()
        return "No hay ninguna instalación pendiente (o ya venció). Pídemela de nuevo."
    id_, nombre = _pendiente["id"], _pendiente["nombre"]
    _pendiente.clear()
    if not _ID_WINGET.fullmatch(id_):
        return "El id del paquete no es válido; no instalé nada."
    cmd = [tools_pc._winget(), "install", "--id", id_, "--exact", "--source", "winget", "--scope", "user",
           "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=900, creationflags=_SIN_VENTANA)
    except subprocess.TimeoutExpired:
        return f"La instalación de {nombre} superó el tiempo límite. Revisa si WinGet sigue trabajando."
    except Exception as e:
        return f"No pude instalar {nombre}: {e}"
    if r.returncode == 0:
        try:
            apps_index.cargar(forzar=True)
        except Exception:
            pass
        return f"Instalé {nombre} para tu usuario."
    return (f"No instalé {nombre}. Puede que el paquete no admita instalación solo para tu usuario (no hago instalaciones "
            "para todo el equipo) o que ya esté instalado. " + tools_pc._limpiar(r.stdout + "\n" + r.stderr, 6)[-300:])


def cancelar_instalacion() -> str:
    hubo = bool(_pendiente)
    _pendiente.clear()
    return "Listo, no instalo nada." if hubo else "No había ninguna instalación pendiente."


def hay_pendiente() -> bool:
    return bool(_pendiente) and time.time() - _pendiente.get("ts", 0) <= _VIGENCIA


def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


SPEC = [
    _t("confirmar_instalacion", "Instala la aplicación de WinGet que instalar_app propuso. Solo después de que el usuario diga que sí", {}, []),
    _t("cancelar_instalacion", "Descarta la instalación propuesta por instalar_app (el usuario dijo que no)", {}, []),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in SPEC}
