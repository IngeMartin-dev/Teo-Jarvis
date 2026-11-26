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
- **Los correos se envían de inmediato**, sin pedir confirmación. Para no mandarlos a un desconocido, Jarvis solo usa una dirección que tú hayas escrito en el mensaje, que esté en su memoria («recuerda que el correo de Ana es ana@...») o que sea la de un remitente que acaba de leer. Si no la tiene, no envía y te la pide. Para volver a pedir tu «sí»: `CONFIRMAR_ENVIOS = {"correo": True}` en `config_local.py`.
- El contenido de correos y archivos se trata solo como información: Jarvis no obedece órdenes escritas dentro de un correo.
- Si Gmail pide muchos permisos: Jarvis solo puede leer y enviar (no borra correos); en Drive solo lee y sube archivos.

## Llamadas de WhatsApp, clic por visión, instalador y energía (nuevo)
Con el entorno activo: `python -m pip install -r requirements.txt` (agrega `sounddevice`).

### Contestar llamadas de WhatsApp
- **Cómo funciona:** Jarvis vigila WhatsApp Desktop. Cuando entra una llamada te avisa por voz («Te está llamando X, di contesta y la acepto»).
  - Dices **«Jarvis, contesta»** (o «acepta», «atiende») → la acepta. **«Rechaza»** → la rechaza. **«Yo contesto»** → no hace nada.
  - Si ya viste que suena, también puedes decir **«Jarvis, me están llamando por WhatsApp»**; si en 15 s no dices nada, contesta él.
  - **Si no dices nada en 15 segundos**, Jarvis contesta, dice *«Hola, soy Jarvis, el asistente con IA de Martín. Si se quiere comunicar con él, espere o deje un mensaje»*, **te avisa al celular**, se queda 45 s en la línea, se despide y cuelga.
  - Las **videollamadas no se contestan solas** (para no encender tu cámara): solo te llega el aviso al celular.
  - Mientras hay una llamada, Jarvis no habla en voz alta ni toma como órdenes lo que oye (sale la voz de la otra persona por los parlantes), salvo que digas «Jarvis…».
- **Aviso al celular** (elige uno en `.env`, mira `.env.example`): **ntfy.sh** (instala la app *ntfy*, suscríbete a un tema largo y secreto y ponlo en `NTFY_TOPIC`) o **Telegram** (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`). Prueba con «Jarvis, prueba el aviso al celular».
- **Que quien llama te oiga:** Windows no deja que un programa «hable» dentro de una llamada sin ayuda. Instala un cable de audio virtual gratuito (**VB-CABLE**), en WhatsApp → Ajustes → Voz y video elige *CABLE Output* como micrófono y en `config_local.py` pon `LLAMADA_AUDIO_SALIDA = "CABLE Input"`. Sin eso, Jarvis habla por los parlantes y el micrófono apenas lo capta.
- **Importante, probado sin Windows:** la lógica (cuenta de 15 s, estados, avisos) está probada con pruebas automáticas, pero **los nombres de los botones de WhatsApp los tienes que comprobar tú una vez**: con una llamada sonando di **«Jarvis, diagnostica la llamada»**; te deja en el chat qué ventanas y botones ve. Si tus botones no se llaman «Aceptar / Rechazar / Finalizar», ajusta `LLAMADA_BTN_ACEPTAR`, `LLAMADA_BTN_RECHAZAR` y `LLAMADA_BTN_COLGAR` en `config_local.py`.
- **Contestar siempre sin esperar:** `LLAMADA_ESPERA_SEG = 0` en `config_local.py`. Jarvis contesta en cuanto detecta la llamada, sin avisarte por voz, dice el saludo y te avisa al celular.
- **Opciones** (`config_local.py`): `USUARIO_NOMBRE`, `LLAMADA_ESPERA_SEG`, `LLAMADA_PERMANENCIA_SEG`, `LLAMADA_SALUDO`, `LLAMADAS_AUTO_CONTESTAR = False` (solo avisa, nunca contesta solo), `LLAMADAS_VIGILAR = False`, `PERMISOS = {"llamadas": False}`.

### Clic donde diga la pantalla (sin JSON)
- Si pides tocar algo que no tiene nombre ni está en la lista de controles, Jarvis **mira tu pantalla principal** con un modelo con visión (el proveedor elegido; si falla, prueba los demás con clave) y hace clic donde está: «dale clic al icono rojo de arriba a la derecha». `clic_elemento` cae solo a esto cuando no encuentra el nombre.
- Seguridad: las mismas reglas del control del PC (no actúa sobre terminales, Registro, UAC…), comprueba también **la ventana que hay bajo el punto** donde va a hacer clic, no guarda capturas y el texto que aparezca en la pantalla no se obedece. Si lo que describes parece delicado (pagar, comprar, eliminar, apagar…, ver `CLIC_VISUAL_RIESGO`), **te pregunta antes**. Esquina superior izquierda = parar.
- Con proveedores solo de texto (Cloudflare, Mistral) no puede mirar la pantalla: usa Gemini, Groq, OpenRouter u Ollama con visión.

### Instalar apps: Tienda primero, luego una versión segura
- «Jarvis, instala Spotify»: busca en **Microsoft Store**; si hay una coincidencia clara, la instala.
- Si **no está en la Tienda**, busca en el catálogo de **WinGet** (sus paquetes se revisan y el instalador se verifica con hash) y **te pregunta**: «Encontré X del editor Y, ¿la instalo?». Solo instala si dices que sí.
- Si hay varias parecidas, te las lista y eliges. Si no está en ninguno, te lo dice: **no descarga instaladores de páginas web por su cuenta**.
- Todo se instala solo para tu usuario, sin permisos de administrador.

### Suspender, apagar y reiniciar
- «Jarvis, apaga el computador / reinícialo / suspéndelo». **Siempre te pregunta primero** y solo actúa con tu «sí».
- Apagar y reiniciar tienen **cuenta atrás de 15 s** (`ENERGIA_RETRASO_SEG`): di **«cancela el apagado»** (responde al instante, sin modelo) o `shutdown /a` en una terminal. No fuerza el cierre de programas: si algo tiene trabajo sin guardar, Windows te avisa.
- Suspender usa la API de Windows; si tu PC no suspende, revisa que la suspensión esté activa en Configuración → Energía.
- Apagar el permiso: `PERMISOS = {"energia": False}`.

## Pendiente
- Canva: requiere su API (Canva Connect) y es más complejo; por ahora Jarvis puede abrir Canva en el navegador.

## Control del PC, WhatsApp y Microsoft Store
Instala las librerías nuevas con el entorno activo: `python -m pip install -r requirements.txt`

- **Microsoft Store:** «Jarvis, instala Spotify de la Tienda», «busca WhatsApp en la Tienda», «abre la Tienda». Usa WinGet con la fuente `msstore` (viene con Windows); si pide iniciar sesión, ábrela e inicia sesión una vez.
- **Mouse y teclado:** «haz clic en Aceptar», «escribe hola», «presiona ctrl+c», «baja la página». Prefiere hacer clic por el **nombre** del botón (`clic_elemento`); también hay clic por coordenadas.
- **WhatsApp Desktop:** «Jarvis, mándale a Mamá por WhatsApp que llego tarde». **Se envía de inmediato**, sin pedir confirmación. Lo más fiable es por número: dile «recuerda que el número de Mamá es 300 123 4567» y Jarvis lo usará siempre (un número de 10 dígitos que empieza por 3 se toma como Colombia, +57). Por nombre, busca el chat en WhatsApp y toma el primer resultado, así que con nombres parecidos puede equivocarse de chat. Para volver a pedir tu «sí»: `CONFIRMAR_ENVIOS = {"whatsapp": True}` en `config_local.py`.
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

## Discord (se envía de inmediato, sin pedir confirmación)
Los destinos de Discord van en su **propio archivo, `discord.json`** (junto al código; Git lo ignora). Si no existe, Jarvis lo crea la primera vez copiando `discord.example.json`.
```json
{
  "usuarios": {
    "Mamá": { "alias": ["mami"], "usuario": "mama_usuario" }
  },
  "canales": {
    "general": {
      "alias": ["principal"],
      "servidor": "Mi Servidor",
      "webhook": "https://discord.com/api/webhooks/..."
    }
  }
}
```
- «Jarvis, mándale a mami por Discord que llego tarde» / «escribe en general de Discord que ya subí el avance».
- **`usuarios`** = mensajes directos (`usuario` es el nombre exacto de Discord). **`canales`** = canales de servidor; `servidor` y `webhook` son opcionales.
- **Canal con `webhook` (lo más fiable):** se envía directo por internet, sin abrir Discord. Créalo en Ajustes del canal → Integraciones → Webhooks → Nuevo webhook → Copiar URL y pégalo en `discord.json`. Sale sin menciones (@everyone, @usuario) por seguridad. Los webhooks son secretos: Jarvis nunca los guarda ni los muestra, los pegas tú.
- **Usuario, o canal sin webhook:** usa Discord Desktop (Ctrl+K), que debe estar abierto con la sesión iniciada. Antes de escribir **comprueba por el título de la ventana que se abrió el chat correcto** (y el servidor, si lo pusiste); si no puede comprobarlo, no envía y te lo dice. Si tu Discord no muestra el servidor en la ventana, borra el campo `servidor`.
- **Seguridad:** solo coincide el nombre o alias completo (sin tildes ni mayúsculas), sin adivinar; si un nombre coincide con un usuario y un canal, pide aclarar. Los elementos con `"ejemplo": true` son de muestra y no se les envía nada: pon los datos reales y borra esa línea.
- **Alias → nombre real:** lo que dices («bolso», «sala uno») solo elige la entrada; a Discord siempre se le busca el nombre real. Usuario: campo `usuario` (y `nombre_visible` = cómo se ve en el chat). Canal o sala: campo `nombre`. Ej.: `"Sala 1": {"nombre": "general"}` hace que «únete a sala uno» entre al canal de voz «general». «Sala uno» y «sala 1» son lo mismo, y el servidor acepta escrituras parecidas (el reconocimiento de voz se equivoca: «pppoe causas» ≈ «tp causas»).
- **Servidores:** en `discord.json` escribes tú cada servidor en `servidores`, con sus `canales` (donde Jarvis escribe, con `webhook` opcional) y sus `salas` (canales de voz). Dices «escribe en general de Mi Servidor» o «entra a la sala Gamer de Mi Servidor». Si el mismo nombre existe en dos servidores y no dices cuál, Jarvis pregunta. Cada servidor acepta `alias`.
- **Llamadas:** «Jarvis, entra a la llamada Sala 1 de Discord» abre Discord Desktop, busca el canal de voz por su nombre (Ctrl+K con «!») y entra. Comprueba por el título de la ventana que sea esa sala (y el servidor, si lo pones). La sección `salas` de `discord.json` es opcional: sirve para dar alias y servidor.
- Para guardar: edita el archivo o dile «guarda a Juan en Discord, su usuario es juan123». Solo guarda datos que tú escribiste en el mensaje.
- Los webhooks `DISCORD_WEBHOOK_<NOMBRE>` del `.env` siguen funcionando para nombres que no estén en `discord.json`.
- **Confirmación:** Discord, WhatsApp y correo se envían sin preguntar (los dos últimos se pueden volver a poner con `CONFIRMAR_ENVIOS`).
- Opciones en `config_local.py`: `PERMISOS = {"discord": False}` lo apaga; `DISCORD_VERIFICAR_TITULO = False` desactiva la comprobación del título (solo si tu Discord no muestra el nombre del chat en la ventana).

## Contactos (`contactos.json`)
Para no tener que decir números ni correos, Jarvis busca a las personas en `contactos.json` (junto al código). Si no existe, lo crea la primera vez copiando `contactos.example.json`. Git **lo ignora** porque tiene datos personales.
```json
{
  "Mamá": {
    "alias": ["mami", "mama"],
    "whatsapp": "+57 300 123 4567",
    "correo": "mama@gmail.com"
  }
}
```
- Todos los campos son opcionales. `alias` son otros nombres con los que la llamas.
- «Jarvis, mándale un WhatsApp a Mamá que llego tarde» / «escríbele un correo a mami...» : busca el nombre (o un alias) en este archivo y usa su número o correo (Discord tiene su propio archivo, `discord.json`). Con WhatsApp usa el número directo, sin buscar el chat por nombre, que es lo más fiable.
- Para guardar: edita el archivo a mano o dile «guarda a Pedro con el número +57 300 111 2233 y el correo pedro@gmail.com». Solo guarda datos que tú escribiste en el mensaje.
- **Seguridad:** solo coincide el nombre o alias completo (sin importar mayúsculas ni tildes), sin adivinar. Si el nombre coincide con varios contactos, pide aclarar en vez de elegir. Los números que terminan en ceros y los correos `@example.com` son de ejemplo y Jarvis no les envía nada. Al listar o consultar contactos, el modelo solo ve los números ocultados (últimos 3 dígitos) y los correos recortados; la lista completa no se le envía. Ojo: lo que tú le dices en el chat sí va al proveedor de IA que elijas (Ollama es local).
- Si el JSON tiene un error de coma o comillas, Jarvis te dice la línea.
