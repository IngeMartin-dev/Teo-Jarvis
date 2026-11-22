# Jarvis v2 (Python + Ollama, gratis y local)

## Actualizar desde la v1
1. Copia estos archivos sobre los de tu carpeta `jarvis` (reemplaza todos).
2. Crea `config_local.py` junto a `config.py` con tu modelo, por ejemplo:
   `MODEL = "el-nombre-de-tu-modelo"`   (mira el nombre exacto con `ollama list`)
3. Con el entorno activo: `python -m pip install -r requirements.txt`
4. Ejecuta: `python main.py`

## Elegir el motor de IA
Al iniciar Jarvis aparece una ventana para elegir **Local (Ollama)**, **Gemini**, **Groq**, **OpenRouter gratis**, **Mistral** o **Cloudflare Workers AI**. La selección se hace en cada inicio.

- Gemini: crea una clave en [Google AI Studio](https://aistudio.google.com/apikey). Jarvis usa `gemini-3.8-flash`, con uso gratis y capacidades para agentes. Los modelos Gemini 2.5 tienen acceso restringido para proyectos nuevos.
- Groq: crea una clave en [Groq Console](https://console.groq.com/keys) usando el plan **Free**. Jarvis usa `openai/gpt-oss-20b`, disponible con llamadas a herramientas. El plan Free tiene límites de uso; si los alcanzas, la API rechaza solicitudes. No cambies al plan Developer si quieres mantenerlo gratis.
- OpenRouter gratis: crea una clave en [OpenRouter](https://openrouter.ai/settings/keys). Jarvis usa `openrouter/free`, que escoge un modelo gratuito compatible con herramientas e imágenes cuando esté disponible. La capa gratuita tiene límites de uso y disponibilidad variables; consulta sus [límites actuales](https://openrouter.ai/docs/api-reference/limits).
- Mistral: Jarvis usa la API directa de Mistral con `mistral-small-latest`. Agrega tu clave en `MISTRAL_API_KEY`. La API para desarrolladores requiere activar facturación y puede generar cargos; el modo gratuito de Mistral no incluye acceso a su API.
- Cloudflare Workers AI: crea un token con permiso **Workers AI: Read** y ten a mano el **Account ID** de Cloudflare. Al elegirlo, Jarvis los pide y guarda como `CLOUDFLARE_API_TOKEN` y `CLOUDFLARE_ACCOUNT_ID` en `.env`. Usa `@cf/openai/gpt-oss-20b`, compatible con herramientas. El plan gratuito incluye 10.000 Neurons diarios; el límite se reinicia a las 00:00 UTC. Este modelo solo acepta texto, no analiza capturas de pantalla.
- Al elegir un proveedor API por primera vez, Jarvis pide la clave y la guarda en `.env`, que está excluido de Git. También puedes colocar las claves manualmente allí para alternar entre proveedores.

Las claves son independientes: `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY` y `CLOUDFLARE_API_TOKEN`; Cloudflare también necesita `CLOUDFLARE_ACCOUNT_ID`. No compartas ni subas `.env` al repositorio.

Si el proveedor elegido rechaza una solicitud por cuota, credenciales, capacidad o error del servicio, Jarvis intenta automáticamente otros proveedores configurados (OpenRouter, Cloudflare, Gemini, Groq y Ollama). Mistral directo solo se usa si lo eliges, para evitar cargos inesperados. El respaldo respeta las capacidades de cada modelo; por ejemplo, omite los modelos de solo texto al analizar una captura.

## Novedades
- **Conversación continua**: dices «Hola Jarvis» una vez y sigue escuchando sin repetirlo. Para terminar: «adiós Jarvis», «eso es todo» o «descansa». Si quieres que vuelva solo a reposo tras X segundos de silencio, pon `CONVERSATION_TIMEOUT = 120` en `config_local.py`.
- **Orbe animado** en la esquina inferior derecha, sobre la barra de Windows: azul = escuchando, ámbar = pensando, verde = hablando. Clic en el orbe abre el chat.
- **Abre y cierra aplicaciones** por nombre. Solo cierra procesos de tu sesión y protege los procesos de Windows.
- **Instala aplicaciones a petición** usando WinGet, desde su fuente oficial, con ámbito de usuario y sin elevar permisos. Si el paquete exige instalarse para todo el equipo, Jarvis lo rechaza.
- **Ve la pantalla a petición**: si preguntas qué aparece o pides leerla, toma una captura temporal en memoria y la analiza con el proveedor activo. Con Groq usa Qwen 3.8 27B, compatible con imágenes y herramientas. No guarda capturas ni interactúa con la pantalla.
- **Archivos**: buscar, abrir, listar, leer (txt, código, docx) y crear carpetas en tus carpetas de usuario; protege Windows, Program Files, ProgramData, AppData y claves (.ssh). No borra ni mueve archivos ni ejecuta comandos arbitrarios.
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

## Control del PC, WhatsApp y Microsoft Store
Instala las librerías nuevas con el entorno activo: `python -m pip install -r requirements.txt`

- **Microsoft Store:** «Jarvis, instala Spotify de la Tienda», «busca WhatsApp en la Tienda», «abre la Tienda». Usa WinGet con la fuente `msstore` (viene con Windows); si pide iniciar sesión, ábrela e inicia sesión una vez.
- **Mouse y teclado:** «haz clic en Aceptar», «escribe hola», «presiona ctrl+c», «baja la página». Prefiere hacer clic por el **nombre** del botón (`clic_elemento`); también hay clic por coordenadas.
- **WhatsApp Desktop:** «Jarvis, mándale a Mamá por WhatsApp que llego tarde». Escribe el mensaje en el chat, tú lo revisas en pantalla y **solo se envía cuando dices «sí» / «envíalo»**. Por número usa el indicativo (un número de 10 dígitos que empieza por 3 se toma como Colombia, +57).
- **Seguridad:** mueve el mouse a la **esquina superior izquierda** de la pantalla para detener cualquier acción. Jarvis no actúa sobre terminales, el cuadro Ejecutar, el Registro, el Administrador de tareas ni avisos de UAC, y no escribe en ventanas de contraseña o inicio de sesión.
- **Apagar permisos:** en `config_local.py` pon, por ejemplo, `PERMISOS = {"control_pc": False, "whatsapp": True, "tienda": True}`.

## Programar y modificar archivos desde VS Code
- **Qué hace:** «Jarvis, crea un proyecto web llamado portafolio y hazme una página con mi nombre», «en mi-tienda agrégale una función que sume dos números a main.py», «cambia el color del botón a azul en style.css», «busca dónde uso la palabra precio», «ábreme main.py en VS Code», «deshaz el último cambio». Cada archivo que crea o edita se abre en VS Code (línea incluida). Para subirlo, «sube los cambios de portafolio».
- **Dónde trabaja:** en `~/Proyectos` (cada carpeta es un proyecto). Para que también pueda editar otras carpetas, por ejemplo el propio Jarvis, agrégalas en `config_local.py`: `CODIGO_RAICES = [r"C:\Users\POWER\jarvis"]`.
- **Seguridad:** solo toca esas carpetas, no sale con `..`, no toca `.git` ni Windows, no lee ni escribe `.env`, `credentials.json`, `token.json` ni claves. Antes de cambiar un archivo guarda una copia en `~/.jarvis/backups` y «deshacer» la restaura. **No ejecuta código**: solo lo escribe y lo abre.
- **Privacidad:** con Gemini o Groq, el código que Jarvis lee se envía a esa nube para poder responder. Con Ollama (local) no sale de tu PC.
- **Opciones:** `PERMISOS = {"codigo": False}` lo apaga; `CODIGO_ABRIR_VSCODE = False` evita que abra VS Code tras cada cambio.
- Si dice que no encuentra `code`: en VS Code, Ctrl+Shift+P → «Shell Command: Install 'code' command in PATH».

## Groq: rotación automática de modelos (error 429)
Con **Groq** elegido, si un modelo responde 429 (límite gratuito), Jarvis pasa al siguiente de la lista `GROQ_MODELS` de `config.py` **sin avisarte** y sigue la conversación. Solo si **todos** dan 429 ves el error 429. Los modelos que acaban de dar 429 se saltan un rato (el tiempo que indica Groq) y se vuelven a probar.
- Cualquier otro error (400, 401...) **no cambia de modelo**: se muestra tal cual; los 5xx y fallos de red se reintentan hasta 3 veces con el mismo modelo.
- Con Groq elegido no se salta a otros proveedores: la cadena entre proveedores solo aplica a los demás.
- Para ver la pantalla se usan solo los modelos de `GROQ_VISION_MODELS`.
