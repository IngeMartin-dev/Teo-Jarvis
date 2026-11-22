"""Enviar mensajes a Discord desde Jarvis. SE ENVÍAN DE INMEDIATO, sin pedir confirmación.

Dos formas, Jarvis elige sola:
1) Webhook de un canal (la más fiable): en tu servidor → Ajustes del canal → Integraciones → Webhooks → Nuevo webhook →
   Copiar URL, y la pegas en el archivo .env con el nombre del canal:
       DISCORD_WEBHOOK_GENERAL=https://discord.com/api/webhooks/...
       DISCORD_WEBHOOK_AVISOS=https://discord.com/api/webhooks/...
   Luego: «mándale a general en Discord que ya subí el avance». Solo sirve para canales de servidor, no para mensajes directos.
2) Discord Desktop (para mensajes directos y cualquier canal): abre Discord, busca el destino con Ctrl+K, comprueba por el
   título de la ventana que se abrió el chat correcto y recién entonces escribe y envía. Si no puede comprobarlo, NO envía.

Opciones (config_local.py): PERMISOS = {"discord": False} lo apaga; DISCORD_VERIFICAR_TITULO = False desactiva la comprobación
del título (solo si tu Discord no muestra el nombre del chat en la ventana).
"""
import os, re, time
import requests
import apps_index, config

_HOOK = re.compile(r"^https://(?:ptb\.|canary\.)?(?:discord|discordapp)\.com/api/webhooks/\d+/[\w-]+/?$")


def _permiso(nombre: str):
    if getattr(config, "PERMISOS", {}).get(nombre, True):
        return None
    return f"El permiso '{nombre}' está desactivado en la configuración (PERMISOS)."


def _webhooks() -> dict:
    """nombre normalizado -> url, desde variables DISCORD_WEBHOOK_<NOMBRE> del .env."""
    res = {}
    for k, v in os.environ.items():
        if k.upper().startswith("DISCORD_WEBHOOK_") and v.strip():
            res[apps_index._norm(k[len("DISCORD_WEBHOOK_"):].replace("_", " "))] = v.strip()
    return res


def _por_webhook(url: str, mensaje: str, nombre: str) -> str:
    if not _HOOK.match(url):
        return f"El webhook de «{nombre}» en el .env no tiene un formato válido de Discord."
    try:
        r = requests.post(url, json={"content": mensaje, "allowed_mentions": {"parse": []}}, timeout=20)
    except requests.RequestException as e:
        return f"No pude conectar con Discord: {e}"
    if r.status_code in (200, 204):
        return f"Mensaje enviado a #{nombre} en Discord."
    if r.status_code == 429:
        return "Discord me pidió esperar un momento (límite de mensajes). Inténtalo de nuevo en unos segundos."
    if r.status_code in (401, 404):
        return f"El webhook de «{nombre}» ya no existe o es inválido; crea uno nuevo y actualiza el .env."
    return f"Discord respondió con error {r.status_code}: {r.text[:150]}"


def _discord_al_frente(segundos: float = 15) -> bool:
    import tools_pc
    fin = time.time() + segundos
    while time.time() < fin:
        t, exe = tools_pc._ventana()
        if "discord" in t.lower() or "discord" in exe:
            return True
        time.sleep(0.5)
    return False


def _por_escritorio(destino: str, mensaje: str, tipo: str) -> str:
    import tools, tools_pc
    if (m := _permiso("control_pc")):
        return m
    prefijo = "" if destino[:1] in "@#!*" else {"usuario": "@", "canal": "#"}.get(tipo, "")
    limpio = destino.lstrip("@#!*").strip()
    try:
        tools.abrir_app("discord")
        if not _discord_al_frente():
            return "No pude abrir Discord Desktop o no se puso al frente. ¿Está instalado y con la sesión iniciada?"
        time.sleep(2.0)
        pg = tools_pc._pg()
        pg.hotkey("ctrl", "k"); time.sleep(0.7)            # buscador rápido de Discord
        tools_pc._pegar(prefijo + limpio); time.sleep(1.4)
        pg.press("enter"); time.sleep(1.6)
        if getattr(config, "DISCORD_VERIFICAR_TITULO", True):
            titulo, exe = tools_pc._ventana()
            if "discord" not in titulo.lower() and "discord" not in exe:
                return "Discord dejó de estar al frente; no envié nada."
            if apps_index._norm(limpio) not in apps_index._norm(titulo):
                return (f"No pude confirmar que se abrió el chat de «{limpio}» (la ventana dice «{titulo}»), así que no envié nada para "
                        "no mandarlo a la persona o canal equivocado. Dime el nombre exacto tal como aparece en Discord.")
        tools_pc._pegar(mensaje); time.sleep(0.4)
        pg.press("enter")
        return f"Mensaje enviado a {prefijo}{limpio} en Discord."
    except Exception as e:
        return f"No pude enviar el mensaje por Discord: {e}"


def enviar_discord(destino: str, mensaje: str, tipo: str = "") -> str:
    """Envía un mensaje a Discord AHORA MISMO (sin pedir confirmación). destino = canal con webhook, usuario o canal."""
    if (m := _permiso("discord")):
        return m
    destino, mensaje = destino.strip(), mensaje.strip()
    if not destino or len(destino) > 80 or not mensaje:
        return "Necesito un destino (canal o persona) y el mensaje."
    if len(mensaje) > 2000:
        return "Discord solo permite mensajes de hasta 2000 caracteres; acórtalo."
    hooks = _webhooks()
    clave = apps_index._norm(destino.lstrip("#"))
    if clave in hooks and tipo != "usuario":
        return _por_webhook(hooks[clave], mensaje, destino.lstrip("#"))
    import contactos
    valor, err = contactos.resolver(destino, "discord")
    if err:
        return err
    if valor:  # contacto con usuario de Discord guardado: se usa ese nombre exacto
        destino, tipo = valor, "usuario"
    return _por_escritorio(destino, mensaje, tipo)


# ------------------------------ Registro para el LLM ------------------------------
def _t(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


S = {"type": "string"}
SPEC = [
    _t("enviar_discord", "Envía un mensaje a Discord de inmediato, sin pedir confirmación. destino = nombre del canal, o del usuario "
                         "para un mensaje directo; tipo = usuario o canal si el usuario lo aclara",
       {"destino": S, "mensaje": S, "tipo": {"type": "string", "enum": ["usuario", "canal"]}}, ["destino", "mensaje"]),
]
REGISTRY = {f["function"]["name"]: globals()[f["function"]["name"]] for f in SPEC}
