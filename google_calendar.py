"""Google Calendar para Jarvis.
Autoriza una sola vez ejecutando:  python google_calendar.py
Necesita ~/.jarvis/credentials.json (ver README, sección Google Calendar).
"""
from datetime import datetime, timedelta, timezone
import config

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CRED = config.DATA_DIR / "credentials.json"
TOKEN = config.DATA_DIR / "token.json"


def _servicio():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds or not creds.valid:
            if not CRED.exists():
                raise FileNotFoundError(f"Falta el archivo {CRED}. Sigue la sección Google Calendar del README.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED), SCOPES)
            creds = flow.run_local_server(port=0)  # abre el navegador para que inicies sesión
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def crear_evento(titulo: str, inicio_iso: str, duracion_min: int = 60) -> str:
    ini = datetime.fromisoformat(inicio_iso)
    fin = ini + timedelta(minutes=int(duracion_min or 60))
    cuerpo = {
        "summary": titulo,
        "start": {"dateTime": ini.isoformat(), "timeZone": config.TIMEZONE},
        "end": {"dateTime": fin.isoformat(), "timeZone": config.TIMEZONE},
    }
    _servicio().events().insert(calendarId="primary", body=cuerpo).execute()
    return f"Listo, agendé «{titulo}» para el {ini:%d/%m/%Y a las %H:%M}."


def proximos(cantidad: int = 5) -> str:
    ahora = datetime.now(timezone.utc).isoformat()
    r = _servicio().events().list(calendarId="primary", timeMin=ahora, maxResults=int(cantidad or 5),
                                  singleEvents=True, orderBy="startTime").execute()
    items = r.get("items", [])
    if not items:
        return "No tienes eventos próximos."
    return "\n".join(f"{e['start'].get('dateTime', e['start'].get('date'))}: {e.get('summary', '(sin título)')}" for e in items)


if __name__ == "__main__":
    _servicio()
    print("Google Calendar autorizado correctamente.")
