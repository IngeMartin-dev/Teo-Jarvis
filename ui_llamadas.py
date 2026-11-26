"""Ventana de llamada de WhatsApp Desktop (solo Windows): detectar, aceptar, rechazar y colgar.

Usa UI Automation (pywinauto), igual que clic_elemento. Solo toca ventanas que pertenecen a WhatsApp y busca los
botones por su NOMBRE (configurable en config.LLAMADA_BTN_*), no por coordenadas.

Cada función devuelve datos simples para que llamadas.py (la lógica) se pueda probar sin Windows.
"""
import ctypes, re, time
from ctypes import wintypes
from pathlib import Path
import config

_GENERICOS = re.compile(r"whatsapp|llamada|call|voz|voice|video|entrante|incoming|llamando|calling|ringing|timbrando|"
                        r"aceptar|rechazar|accept|decline", re.I)


def _rx(nombre: str) -> "re.Pattern":
    return re.compile(getattr(config, nombre), re.I)


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
    """Ventanas visibles de nivel superior de WhatsApp (o todas con solo=False): [{hwnd, titulo, exe, w, h}]."""
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
                res.append({"hwnd": hwnd, "titulo": buf.value, "exe": exe, "w": r.right - r.left, "h": r.bottom - r.top})
        except Exception:
            pass
        return True

    u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return res


def _candidatas() -> list:
    """Ventanas de WhatsApp que pueden ser una llamada: pequeñas (aviso o ventana de llamada) o con «llamada» en el título.
    Así no se recorre cada segundo el árbol enorme de la ventana principal."""
    max_w, max_h = getattr(config, "LLAMADA_VENTANA_MAX", (700, 500))
    return [v for v in ventanas_whatsapp()
            if (0 < v["w"] <= max_w or 0 < v["h"] <= max_h) or re.search(r"llamada|call", v["titulo"], re.I)]


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


def _nombre_llamante(textos: list) -> str:
    for t in textos:
        if 1 < len(t) <= 60 and not _GENERICOS.search(t):
            return t
    return ""


def buscar_llamada():
    """None si no hay llamada, o {'tipo': 'entrante'|'activa', 'nombre', 'video', 'hwnd'}."""
    ok_acep, ok_colg = _rx("LLAMADA_BTN_ACEPTAR"), _rx("LLAMADA_BTN_COLGAR")
    for v in _candidatas():
        try:
            botones = [n for n, _e in _controles(v["hwnd"], "Button")]
            if any(ok_acep.search(n) for n in botones):
                tipo = "entrante"
            elif any(ok_colg.search(n) for n in botones):
                tipo = "activa"
            else:
                continue
            textos = [n for n, _e in _controles(v["hwnd"], "Text")]
        except Exception:
            continue
        todo = " ".join(textos + botones + [v["titulo"]])
        return {"tipo": tipo, "hwnd": v["hwnd"], "nombre": _nombre_llamante(textos),
                "video": bool(re.search(r"video", todo, re.I))}
    return None


def _pulsar(patron: str) -> bool:
    rx = _rx(patron)
    for v in _candidatas():
        try:
            for nombre, e in _controles(v["hwnd"], "Button"):
                if rx.search(nombre):
                    try:
                        e.invoke()
                    except Exception:
                        e.click_input()
                    return True
        except Exception:
            continue
    return False


def aceptar() -> bool:
    return _pulsar("LLAMADA_BTN_ACEPTAR")


def rechazar() -> bool:
    return _pulsar("LLAMADA_BTN_RECHAZAR")


def colgar() -> bool:
    return _pulsar("LLAMADA_BTN_COLGAR")


_SHELL = {"shellexperiencehost.exe", "applicationframehost.exe", "startmenuexperiencehost.exe", "searchhost.exe"}


def instantanea() -> list:
    """Líneas que describen lo que hay en pantalla ahora, para el diagnóstico de llamadas. Por privacidad solo muestra el
    TÍTULO de las ventanas de WhatsApp, las pequeñas (avisos y ventanas emergentes) y las del shell de Windows (avisos);
    de las demás solo el programa."""
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
                try:
                    lineas.append("    botones: " + (" | ".join(n for n, _e in _controles(v["hwnd"], "Button")[:15]) or "(ninguno)"))
                    lineas.append("    textos: " + (" | ".join(n for n, _e in _controles(v["hwnd"], "Text")[:10]) or "(ninguno)"))
                except Exception as e:
                    lineas.append(f"    no pude leer sus controles: {type(e).__name__}: {e}")
        else:
            lineas.append(f"[{v['exe'] or '?'}] (ventana grande, título oculto) {v['w']}x{v['h']}")
    return lineas


def diagnostico() -> str:
    """Qué ve Jarvis en las ventanas de WhatsApp. Úsalo con una llamada sonando para ajustar los nombres de botones."""
    try:
        vs = ventanas_whatsapp()
    except Exception as e:
        return f"No pude listar las ventanas: {e}"
    if not vs:
        return "No veo ninguna ventana de WhatsApp. ¿Está abierto?"
    cand = {v["hwnd"] for v in _candidatas()}
    lineas, fin = [], time.time() + 12
    for v in vs:
        marca = "candidata" if v["hwnd"] in cand else "ignorada (grande)"
        lineas.append(f"Ventana «{v['titulo']}» [{v['exe']}] {v['w']}x{v['h']} — {marca}")
        if v["hwnd"] in cand and time.time() < fin:
            try:
                lineas.append("  Botones: " + (" | ".join(n for n, _e in _controles(v["hwnd"], "Button")[:15]) or "(ninguno)"))
                lineas.append("  Textos: " + (" | ".join(n for n, _e in _controles(v["hwnd"], "Text")[:10]) or "(ninguno)"))
            except Exception as e:
                lineas.append(f"  No pude leer sus controles: {e}")
    return "\n".join(lineas)[:1800]
