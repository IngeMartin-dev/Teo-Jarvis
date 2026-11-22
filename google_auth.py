"""Autorización de Google compartida (Calendar + Gmail + Drive) con un solo inicio de sesión.
Ejecuta una vez:  python google_auth.py
Si ya habías autorizado solo Calendar, borra ~/.jarvis/token.json antes (se pedirán los permisos nuevos).
"""
import config

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",   # crear y ver eventos
    "https://www.googleapis.com/auth/gmail.readonly",    # leer correos
    "https://www.googleapis.com/auth/gmail.send",        # enviar correos
    "https://www.googleapis.com/auth/drive.readonly",    # buscar y leer archivos de Drive
    "https://www.googleapis.com/auth/drive.file",        # subir archivos a Drive
]
CRED = config.DATA_DIR / "credentials.json"
TOKEN = config.DATA_DIR / "token.json"


def credenciales():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and not set(SCOPES) <= set(creds.scopes or []):
        creds = None  # el token viejo no tiene todos los permisos: volver a autorizar
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds or not creds.valid:
            if not CRED.exists():
                raise FileNotFoundError(f"Falta el archivo {CRED}. Sigue la sección Google del README.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED), SCOPES)
            creds = flow.run_local_server(port=0)  # abre el navegador; marca TODAS las casillas de permisos
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def servicio(api: str, version: str):
    from googleapiclient.discovery import build
    return build(api, version, credentials=credenciales(), cache_discovery=False)


if __name__ == "__main__":
    credenciales()
    print("Google autorizado: Calendar, Gmail y Drive listos.")
