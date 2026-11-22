"""Google Calendar para Jarvis (usa la autorización compartida de google_auth.py).
Autoriza una sola vez con:  python google_auth.py
"""
from datetime import datetime, timedelta, timezone
import config, google_auth


def _servicio():
    return google_auth.servicio("calendar", "v3")


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


def _linea(e: dict) -> str:
    ini = e["start"].get("dateTime")
    hora = datetime.fromisoformat(ini).strftime("%d/%m %H:%M") if ini else "Todo el día"
    return f"{hora}: {e.get('summary', '(sin título)')}"


def proximos(cantidad: int = 5) -> str:
    ahora = datetime.now(timezone.utc).isoformat()
    r = _servicio().events().list(calendarId="primary", timeMin=ahora, maxResults=int(cantidad or 5),
                                  singleEvents=True, orderBy="startTime").execute()
    items = r.get("items", [])
    return "\n".join(_linea(e) for e in items) if items else "No tienes eventos próximos."


def hoy() -> str:
    ini = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    r = _servicio().events().list(calendarId="primary", timeMin=ini.isoformat(),
                                  timeMax=(ini + timedelta(days=1)).isoformat(),
                                  singleEvents=True, orderBy="startTime").execute()
    items = r.get("items", [])
    return "\n".join(_linea(e) for e in items) if items else "No tienes eventos hoy."


if __name__ == "__main__":
    google_auth.credenciales()
    print("Google autorizado correctamente.")
