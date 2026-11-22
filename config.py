"""Configuración de Jarvis. Edita este archivo a tu gusto."""
from pathlib import Path

HOME = Path.home()
DATA_DIR = HOME / ".jarvis"
DATA_DIR.mkdir(exist_ok=True)

# --- Cerebro (Ollama local) ---
OLLAMA_URL = "http://localhost:11434/api/chat"
# Modelos recomendados con soporte de herramientas: "qwen2.5:7b", "llama3.1:8b"
# Si tu PC es modesta: "qwen2.5:3b" o "llama3.2:3b"
MODEL = "qwen3.5:4b"

# --- Voz ---
WAKE_PHRASES = ["hola jarvis", "oye jarvis", "jarvis"]
LANG = "es-ES"
VOICE_ENABLED = True

# --- Carpetas ---
PROJECTS_DIR = HOME / "Proyectos"      # donde se crean los proyectos de código
DOCS_DIR = HOME / "Documents" / "Jarvis"  # donde se guardan Word/Excel/PowerPoint
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

# --- Apps conocidas (nombre -> comando de Windows) ---
APPS = {
    "whatsapp": "whatsapp:",            # protocolo de WhatsApp Desktop (Microsoft Store)
    "vscode": "code",
    "chrome": "chrome",
    "excel": "excel",
    "word": "winword",
    "powerpoint": "powerpnt",
    "calculadora": "calc",
    "bloc de notas": "notepad",
}
