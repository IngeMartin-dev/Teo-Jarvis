"""Avisos al celular: ntfy.sh (sin cuenta) o Telegram. Se configuran en .env (ver .env.example).

ntfy: instala la app «ntfy» en el celular, suscríbete a un tema con un nombre largo y secreto (es como una contraseña:
quien lo conozca puede leer tus avisos) y pon ese nombre en NTFY_TOPIC.
Telegram: crea un bot con @BotFather, escríbele «hola» y pon el token en TELEGRAM_BOT_TOKEN y tu id en TELEGRAM_CHAT_ID.
"""
import requests
import config


def canal() -> str:
    """'ntfy', 'telegram' o '' si no hay ninguno configurado."""
    if getattr(config, "NTFY_TOPIC", ""):
        return "ntfy"
    if getattr(config, "TELEGRAM_BOT_TOKEN", "") and getattr(config, "TELEGRAM_CHAT_ID", ""):
        return "telegram"
    return ""


def avisar_celular(mensaje: str, titulo: str = "Jarvis", urgente: bool = False) -> tuple:
    """Envía un aviso al celular. Devuelve (ok, texto). Nunca incluye claves ni el tema en los errores."""
    mensaje = (mensaje or "").strip()[:1000]
    if not mensaje:
        return False, "No hay nada que avisar."
    c = canal()
    if not c:
        return False, ("No tengo configurado el aviso al celular. Pon NTFY_TOPIC (ntfy.sh) o "
                       "TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en el archivo .env.")
    try:
        if c == "ntfy":
            servidor = (getattr(config, "NTFY_SERVER", "") or "https://ntfy.sh").rstrip("/")
            r = requests.post(servidor + "/", timeout=10, json={
                "topic": config.NTFY_TOPIC, "title": titulo, "message": mensaje,
                "priority": 5 if urgente else 3, "tags": ["telephone_receiver"]})
        else:
            r = requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage", timeout=10,
                              json={"chat_id": config.TELEGRAM_CHAT_ID, "text": f"{titulo}: {mensaje}"})
        if r.status_code == 200:
            return True, "Aviso enviado al celular."
        return False, f"El servicio de avisos respondió con error ({r.status_code}). Revisa la configuración."
    except Exception as e:
        # No se muestra str(e): en Telegram la URL incluye el token.
        return False, f"No pude enviar el aviso al celular ({type(e).__name__}). Revisa tu conexión."
