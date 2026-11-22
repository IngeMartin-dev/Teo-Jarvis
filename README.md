# Jarvis v1 (Python + Ollama, gratis y local)

## Instalación (Windows)
1. **Python 3.11+**: https://www.python.org (marca "Add to PATH").
2. **Ollama**: https://ollama.com → luego en una terminal:
   `ollama pull qwen2.5:7b`  (si tu PC es modesta: `qwen2.5:3b` y cambia `MODEL` en `config.py`).
3. **Dependencias**: dentro de esta carpeta, `pip install -r requirements.txt`
   (si `pyaudio` falla: `pip install pipwin` y `pipwin install pyaudio`).
4. **GitHub**: instala Git (https://git-scm.com) y GitHub CLI (https://cli.github.com), luego `gh auth login`.
5. **Google Calendar** (opcional, fase 2): crea credenciales OAuth en Google Cloud (API de Calendar) y avísale a Claude para generar `google_calendar.py`.
6. **Ejecutar**: `python main.py` → aparece el icono en la bandeja (junto al reloj).
7. **Arrancar con Windows**: `python autostart.py on` (para quitarlo: `python autostart.py off`).

## Qué puedes decirle
- "Hola Jarvis, inicia mi día" → Chrome con Instagram y YouTube + WhatsApp Desktop.
- "Crea un proyecto llamado mi-tienda en web" → carpeta, archivos base, VS Code, repo en GitHub.
- "Sube los cambios de mi-tienda" → commit + push.
- "Hazme un Excel con gastos del mes" / "un Word sobre..." / "una presentación de..."
- "Recuerda que mi cumpleaños es el 3 de mayo" → memoria persistente (`~/.jarvis/memoria.db`).

## Archivos
- `config.py`: modelo, frases clave, rutinas, rutas. Aquí agregas más rutinas.
- `brain.py`: conexión con Ollama y ejecución de herramientas.
- `tools.py`: todo lo que Jarvis puede hacer en tu PC.
- `voice.py`, `main.py`, `memory.py`, `autostart.py`.

## Notas
- La voz usa el reconocimiento de Google (gratis, requiere internet); el cerebro es 100% local.
- Canva y Google Calendar requieren conexión con sus APIs: son la siguiente fase.
# Teo-Jarvis
