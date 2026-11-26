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
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "codestral-latest")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_MODEL = "@cf/zai-org/glm-5.3"
GEMINI_MODEL = "gemini-4-hydrogen"
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_VISION_MODEL = "qwen/qwen3.8-27b"
# Con Groq elegido, si un modelo da 429 Jarvis pasa al siguiente sin avisar. Orden de preferencia:
GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "minimaxai/minimax-m2.7",
    "meta-models/muse-spark-open",
    "llama-3.3-70b-versatile",
]
GROQ_VISION_MODELS = [GROQ_VISION_MODEL]  # modelos que aceptan imágenes (ver la pantalla)
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
        "apps": ["whatsapp", "claude", "visual studio code"],
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

# True = pedir tu «sí» antes de enviar (False = se envía enseguida). Discord siempre se envía enseguida.
CONFIRMAR_ENVIOS = {"correo": False, "whatsapp": False}

# --- Llamadas de WhatsApp (llamadas.py) ---
USUARIO_NOMBRE = "Martín"          # nombre que Jarvis dice al contestar por ti
LLAMADAS_VIGILAR = True            # vigilar llamadas entrantes en WhatsApp Desktop
LLAMADAS_AUTO_CONTESTAR = True     # si no respondes a tiempo, Jarvis contesta por ti (solo llamadas de voz)
LLAMADA_ESPERA_SEG = 3             # segundos que espera antes de contestar él (0 = de inmediato). En ese tiempo puedes decir «contesta», «rechaza» o «yo contesto»
LLAMADA_ANUNCIAR = False           # True = Jarvis te avisa por voz («Te está llamando X, di contesta») y la espera cuenta desde que termina de hablar
LLAMADA_PERMANENCIA_SEG = 45       # cuánto se queda en la línea tras el saludo antes de despedirse y colgar
LLAMADA_SALUDO = ("Hola, soy Jarvis, el asistente con IA de {usuario}. "
                  "Si se quiere comunicar con él, espere o deje un mensaje.")
LLAMADA_DESPEDIDA = "Le avisaré a {usuario} que usted llamó. Hasta luego."
# Para que quien llama oiga a Jarvis hace falta un cable de audio virtual (ver README, «Llamadas de WhatsApp»).
# Pon aquí parte del nombre del dispositivo de salida, por ejemplo "CABLE Input". Vacío = habla por los parlantes.
LLAMADA_AUDIO_SALIDA = "CABLE Input"   # si no tienes VB-CABLE instalado, Jarvis habla por los parlantes
# Nombres de los botones de la ventana de llamada de WhatsApp (expresiones regulares). Si tu WhatsApp usa otros
# textos, corre «Jarvis, diagnostica la llamada» con una llamada sonando y ajústalos en config_local.py.
LLAMADA_BTN_ACEPTAR = r"\b(aceptar|Accept Call|contestar|responder|answer|atender|accept|Accept)\b"
LLAMADA_BTN_RECHAZAR = r"\b(rechazar|decline|reject)\b"
LLAMADA_BTN_COLGAR = r"\b(finalizar|terminar|colgar|end call|hang up|leave call|salir de la llamada)\b"

# --- Energía (energia.py): segundos de cuenta atrás al apagar o reiniciar (5 a 300). Se puede cancelar en ese tiempo. ---
ENERGIA_RETRASO_SEG = 15

# --- Avisos al celular (notificaciones.py). Configura UNO de los dos en .env ---
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")                    # ntfy.sh: sin cuenta; usa un nombre largo y secreto
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")    # Telegram: bot de @BotFather
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Clic por visión (tools_pc.clic_visual) ---
# Si lo que pides tocar coincide con esto, Jarvis pide tu «sí» antes de hacer clic.
CLIC_VISUAL_RIESGO = (r"\b(pagar|pago|comprar|compra|eliminar|borrar|formatear|desinstalar|transferir|"
                      r"enviar dinero|vaciar|apagar|reiniciar|cerrar sesi[oó]n)\b")

try:
    from config_local import *  # type: ignore  # noqa: F401,F403
except ImportError:
    pass
