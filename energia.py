"""Energía del PC: suspender, apagar y reiniciar.

Seguridad:
- Jarvis NUNCA lo hace a la primera: prepara la acción y te pregunta. Solo ejecuta con confirmar_energia, y brain.py
  exige que TU mensaje diga «sí» (no basta con que el modelo lo dé por hecho). La propuesta vence a los 60 s.
- Apagar y reiniciar tienen cuenta atrás (ENERGIA_RETRASO_SEG, 15 s por defecto) y se cancelan al instante con
  «cancela el apagado» (atajo sin modelo, para que responda a tiempo) o con `shutdown /a` en cualquier terminal.
- Nunca fuerza el cierre de programas (no usa /f): si algo tiene trabajo sin guardar, Windows te lo pregunta.
- Se puede apagar con PERMISOS = {"energia": False} en config_local.py.
"""
import re, subprocess, time
import config

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_VIGENCIA = 60
_pendiente: dict = {}
_programada: dict = {}   # apagado/reinicio con cuenta atrás en curso: {"accion", "hasta"}

ACCIONES = {
    "suspender": ("Suspender el PC", "suspenderlo"),
    "apagar": ("Apagar el PC", "apagarlo"),
    "reiniciar": ("Reiniciar el PC", "reiniciarlo"),
}
_ALIAS = {"suspender": "suspender", "suspension": "suspender", "suspensión": "suspender", "dormir": "suspender",
          "sleep": "suspender", "apagar": "apagar", "apaga": "apagar", "shutdown": "apagar",
          "reiniciar": "reiniciar", "reinicia": "reiniciar", "restart": "reiniciar", "reboot": "reiniciar"}


def _permiso():
    if getattr(config, "PERMISOS", {}).get("energia", True):
        return None
    return "El permiso 'energia' está desactivado en la configuración (PERMISOS)."


def _retraso() -> int:
    try:
        return max(5, min(300, int(getattr(config, "ENERGIA_RETRASO_SEG", 15))))
    except (TypeError, ValueError):
        return 15


def _correr(args: list):
    """Ejecuta un comando de Windows. Devuelve (código, salida)."""
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=20, creationflags=_SIN_VENTANA)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def _suspender_ahora():
    """Suspende (no hiberna) con la API de Windows. Devuelve True si el sistema aceptó."""
    import ctypes
    return bool(ctypes.windll.powrprof.SetSuspendState(False, False, False))


def preparar(accion: str) -> str:
    """Deja lista la acción y devuelve el texto para PREGUNTARLE al usuario. No ejecuta nada."""
    if (m := _permiso()):
        return m
    accion = _ALIAS.get((accion or "").strip().lower(), "")
    if not accion:
        return "Puedo suspender, apagar o reiniciar el PC. ¿Cuál de las tres quieres?"
    if _programada:
        return f"Ya hay un {_programada['accion']} en cuenta atrás. Di «cancela el apagado» si quieres detenerlo."
    _pendiente.clear()
    _pendiente.update(accion=accion, ts=time.time())
    extra = "" if accion == "suspender" else (
        f" Tendrás {_retraso()} segundos para cancelarlo y Windows te avisará si hay programas con trabajo sin guardar.")
    return (f"NO hice nada todavía. Pregúntale al usuario, en una frase, si de verdad quiere {ACCIONES[accion][1]}"
            f".{extra} Usa confirmar_energia solo si dice que sí (cancelar_energia si dice que no).")


def confirmar() -> str:
    """Ejecuta la acción preparada. Solo después de que el usuario diga que sí."""
    if (m := _permiso()):
        return m
    if not _pendiente or time.time() - _pendiente.get("ts", 0) > _VIGENCIA:
        _pendiente.clear()
        return "No hay nada pendiente (o ya venció). Pídemelo de nuevo."
    accion = _pendiente["accion"]
    _pendiente.clear()
    try:
        if accion == "suspender":
            return "Suspendiendo el PC." if _suspender_ahora() else "Windows no aceptó suspender el PC (puede que la suspensión esté desactivada)."
        seg = _retraso()
        codigo, salida = _correr(["shutdown", "/s" if accion == "apagar" else "/r", "/t", str(seg),
                                  "/c", "Jarvis: " + ("apagado" if accion == "apagar" else "reinicio") + " solicitado por el usuario"])
        if codigo != 0:
            return f"No pude programar el {accion}: {salida[:200] or 'Windows lo rechazó'}."
        _programada.update(accion=accion, hasta=time.time() + seg)
        return (f"Listo: {'apagando' if accion == 'apagar' else 'reiniciando'} el PC en {seg} segundos. "
                "Di «cancela el apagado» para detenerlo.")
    except Exception as e:
        return f"No pude {accion} el PC: {e}"


def cancelar() -> str:
    """Descarta la propuesta y detiene un apagado/reinicio que esté en cuenta atrás."""
    hubo = bool(_pendiente)
    _pendiente.clear()
    if _programada:
        try:
            codigo, _ = _correr(["shutdown", "/a"])
        except Exception as e:
            return f"No pude cancelar: {e}. Abre una terminal y escribe: shutdown /a"
        accion = _programada.get("accion", "apagado")
        _programada.clear()
        if codigo == 0:
            return f"Cancelé el {accion}."
        return "No había ningún apagado en curso (o ya empezó)."
    return "Listo, no hago nada." if hubo else "No había ninguna acción de energía pendiente."


# Atajo sin modelo: durante la cuenta atrás hay que responder en segundos.
_RE_CANCELAR = re.compile(r"\b(cancela(r|lo)?|det[eé]n(lo|er)?|para(lo)?|aborta(r|lo)?|no\s+(lo\s+)?(apagues|reinicies))\b"
                          r".{0,25}\b(apagado|apagar|reinicio|reiniciar|apaga|reinicia|pc|computador|compu)\b|"
                          r"\bno\s+(apagues|reinicies)\b", re.I)


def manejar_texto(texto: str):
    """Respuesta si el texto cancela un apagado en curso; None si no tiene que ver. Solo actúa si hay algo que cancelar."""
    if (_programada or _pendiente) and _RE_CANCELAR.search(texto or ""):
        if _programada and time.time() > _programada.get("hasta", 0) + 5:
            _programada.clear()   # ya pasó la hora: no hay nada que cancelar
        return cancelar()
    return None


def hay_pendiente() -> bool:
    return bool(_pendiente) and time.time() - _pendiente.get("ts", 0) <= _VIGENCIA


def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


def suspender_pc() -> str:
    return preparar("suspender")


def apagar_pc() -> str:
    return preparar("apagar")


def reiniciar_pc() -> str:
    return preparar("reiniciar")


def confirmar_energia() -> str:
    return confirmar()


def cancelar_energia() -> str:
    return cancelar()


SPEC = [
    _t("suspender_pc", "Prepara suspender el PC (modo de bajo consumo). NO lo hace: devuelve una pregunta de confirmación para el usuario", {}, []),
    _t("apagar_pc", "Prepara apagar el PC. NO lo hace: devuelve una pregunta de confirmación para el usuario", {}, []),
    _t("reiniciar_pc", "Prepara reiniciar el PC. NO lo hace: devuelve una pregunta de confirmación para el usuario", {}, []),
    _t("confirmar_energia", "Suspende, apaga o reinicia el PC según lo preparado. Solo después de que el usuario diga que sí", {}, []),
    _t("cancelar_energia", "Cancela la acción de energía preparada o un apagado/reinicio en cuenta atrás", {}, []),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in SPEC}
