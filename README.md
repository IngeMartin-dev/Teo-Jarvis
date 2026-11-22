# Jarvis v2 (Python + Ollama, gratis y local)

## Actualizar desde la v1
1. Copia estos archivos sobre los de tu carpeta `jarvis` (reemplaza todos).
2. Crea `config_local.py` junto a `config.py` con tu modelo, por ejemplo:
   `MODEL = "el-nombre-de-tu-modelo"`   (mira el nombre exacto con `ollama list`)
3. Con el entorno activo: `python -m pip install -r requirements.txt`
4. Ejecuta: `python main.py`

## Novedades
- **Conversación continua**: dices «Hola Jarvis» una vez y sigue escuchando sin repetirlo. Para terminar: «adiós Jarvis», «eso es todo» o «descansa». Si quieres que vuelva solo a reposo tras X segundos de silencio, pon `CONVERSATION_TIMEOUT = 120` en `config_local.py`.
- **Orbe animado** en la esquina inferior derecha, sobre la barra de Windows: azul = escuchando, ámbar = pensando, verde = hablando. Clic en el orbe abre el chat.
- **Abre cualquier app o juego instalado** por nombre (menú Inicio, escritorio, Steam, apps de la Tienda). Si instalas algo nuevo y no lo encuentra, lo reindexa solo.
- **Archivos**: buscar, abrir, listar, leer (txt, código, docx) y crear carpetas en todo tu PC, excepto Windows, Program Files, ProgramData, AppData y claves (.ssh). No borra ni mueve archivos ni ejecuta comandos libres, a propósito.
- **Excel**: `crear_excel` y `agregar_fila_excel` (agenda.xlsx en Documentos\Jarvis).

## Google Calendar (paso a paso)
1. Entra a https://console.cloud.google.com con tu cuenta de Google y crea un proyecto nuevo llamado «Jarvis».
2. Menú → APIs y servicios → Biblioteca → busca «Google Calendar API» → Habilitar.
3. Menú → APIs y servicios → Pantalla de consentimiento de OAuth (o «Google Auth Platform»):
   nombre «Jarvis», tu correo de asistencia, público «Externo», tu correo de contacto.
   Luego agrega tu Gmail como **usuario de prueba**.
4. Credenciales → Crear credenciales → ID de cliente de OAuth → tipo **Aplicación de escritorio** → Crear → **Descargar JSON**.
5. Renombra ese archivo a `credentials.json` y muévelo a `C:\Users\POWER\.jarvis\` (carpeta oculta que crea Jarvis).
6. Con el entorno activo: `python google_calendar.py` → se abre el navegador → inicia sesión → si dice «Google no ha verificado esta app»: Avanzado → Ir a Jarvis → Permitir.
7. Listo: «Jarvis, agéndame una reunión mañana a las 3 pm».
Nota: mientras la app esté en modo «Prueba», Google caduca la autorización a los 7 días. Para evitarlo: Pantalla de consentimiento → Público → Publicar la app (es solo para ti).

## Pendiente
- Canva: requiere su API (Canva Connect) y es más complejo; por ahora Jarvis puede abrir Canva en el navegador.
