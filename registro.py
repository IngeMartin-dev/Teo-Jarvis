"""Registro de eventos de las llamadas en ~/.jarvis/llamadas.log, para diagnosticar sin adivinar.

Guarda cuándo se detectó una llamada, cuánto tardó cada lectura de WhatsApp, si se pudo aceptar y por qué vía.
Es un archivo local: contiene el nombre de quien llama y títulos de ventanas de WhatsApp. Revísalo antes de compartirlo.
"""
import threading, time
from pathlib import Path
import config

_lock = threading.Lock()
_MAX = 200_000   # bytes; al pasarse se conserva solo la mitad más reciente


def ruta() -> Path:
    return Path(config.DATA_DIR) / "llamadas.log"


def escribir(mensaje: str):
    try:
        with _lock:
            p = ruta()
            if p.exists() and p.stat().st_size > _MAX:
                p.write_text(p.read_text(encoding="utf-8", errors="replace")[-_MAX // 2:], encoding="utf-8")
            with p.open("a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(mensaje).replace("\n", " | ")[:600] + "\n")
    except Exception:
        pass   # el registro nunca debe romper a Jarvis


def cola(n: int = 15) -> list:
    """Las últimas n líneas del registro."""
    try:
        return ruta().read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except Exception:
        return []
