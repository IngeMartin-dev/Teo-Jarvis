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

## Google: Calendar + Gmail + Drive (paso a paso, una sola autorización)
1. Entra a https://console.cloud.google.com con tu cuenta de Google y crea un proyecto llamado «Jarvis» (o usa el que ya tengas).
2. APIs y servicios → Biblioteca → habilita **estas tres**: «Google Calendar API», «Gmail API» y «Google Drive API».
3. Pantalla de consentimiento de OAuth (o «Google Auth Platform»): nombre «Jarvis», tu correo, público «Externo». Agrega tu Gmail como **usuario de prueba**.
   (Opcional: en «Acceso a los datos» agrega los permisos de Calendar, Gmail y Drive que usa Jarvis.)
4. Credenciales → Crear credenciales → ID de cliente de OAuth → **Aplicación de escritorio** → Crear → Descargar JSON.
5. Renómbralo `credentials.json` y muévelo a `C:\Users\POWER\.jarvis\`.
6. Si ya habías autorizado solo Calendar, borra `C:\Users\POWER\.jarvis\token.json`.
7. Con el entorno activo: `python google_auth.py` → se abre el navegador → inicia sesión → si dice «Google no ha verificado esta app»: Avanzado → Ir a Jarvis → **marca todas las casillas de permisos** → Continuar.
8. Listo. Pruébalo: «Jarvis, ¿qué correos nuevos tengo?», «Jarvis, dame mi plan del día», «Jarvis, envíale un correo a ... diciendo ...», «Jarvis, busca mi CV en Drive», «Jarvis, agéndame algo mañana a las 3 pm».
Notas:
- Mientras la app esté en modo «Prueba», Google caduca la autorización a los 7 días; para evitarlo, publica la app desde la pantalla de consentimiento (es solo para ti).
- **Enviar correos pide confirmación**: Jarvis te lee el borrador y solo lo envía cuando respondes «sí», «envíalo», «confirmo» o «dale».
- El contenido de correos y archivos se trata solo como información: Jarvis no obedece órdenes escritas dentro de un correo.
- Si Gmail pide muchos permisos: Jarvis solo puede leer y enviar (no borra correos); en Drive solo lee y sube archivos.

## Pendiente
- Canva: requiere su API (Canva Connect) y es más complejo; por ahora Jarvis puede abrir Canva en el navegador.
