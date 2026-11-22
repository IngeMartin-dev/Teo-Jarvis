"""Configuración de Jarvis.
Para tus cambios personales (modelo, rutas, etc.) crea un archivo config_local.py
junto a este y pon ahí solo las líneas que quieras cambiar, por ejemplo:
    MODEL = "el-nombre-de-tu-modelo"
Así, si actualizas Jarvis, no pierdes tu configuración.
"""
from pathlib import Path
import os

_ENV_FILE = Path(__file__).with_name(".env")
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _name, _value = _line.split("=", 1)
            os.environ.setdefault(_name.strip(), _value.strip().strip("\"'"))

HOME = Path.home()
DATA_DIR = HOME / ".jarvis"
DATA_DIR.mkdir(exist_ok=True)

# --- Cerebro (Ollama local) ---
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:4b"          # tu modelo de Ollama (mira `ollama list`)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_MODEL = "gemini-3.8-flash"
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_VISION_MODEL = "qwen/qwen3.8-27b"
TIMEZONE = "America/Bogota"

# --- Voz ---
# Frase de activación (acepta variantes que el reconocedor suele confundir)
WAKE_REGEX = r"^\s*(?:hola|oye|hey|ey|ok)?[ ,]*(?:jarvis|yarvis|harvis|jarvi|yervis|jarbis|jarves|yarbis)\b[ ,.!¿?]*"
# Tras activarlo, Jarvis sigue escuchando SIN que repitas "hola Jarvis" hasta que digas una de estas:
END_PHRASES = ["adiós jarvis", "adios jarvis", "hasta luego", "eso es todo", "descansa",
               "ya puedes descansar", "modo reposo", "chao jarvis"]
# Segundos de silencio tras los que vuelve a reposo. 0 = nunca (solo con las frases de arriba).
CONVERSATION_TIMEOUT = 0
LANG = "es-CO"
VOICE_ENABLED = True
VOICE_RATE = 185

# --- Carpetas ---
PROJECTS_DIR = HOME / "Proyectos"          # proyectos de código
DOCS_DIR = HOME / "Documents" / "Jarvis"   # Word / Excel / PowerPoint creados por Jarvis
PROJECTS_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# --- Rutinas (frases clave -> acciones) ---
ROUTINES = {
    "inicia mi día": {
        "urls": ["https://www.instagram.com", "https://www.youtube.com"],
        "apps": ["whatsapp"],
        "say": "Buenos días. Todo listo para empezar tu día.",
    },
}

# --- Atajos de apps (opcional). Las demás apps las encuentra solo, por nombre. ---
APPS = {
    "whatsapp": "whatsapp:",
    "vscode": "code",
    "visual studio code": "code",
    "chrome": "chrome",
    "excel": "excel",
    "word": "winword",
    "powerpoint": "powerpnt",
    "calculadora": "calc",
    "bloc de notas": "notepad",
}

try:
    from config_local import *  # type: ignore  # noqa: F401,F403
except ImportError:
    pass
