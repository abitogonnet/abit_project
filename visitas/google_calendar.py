import base64
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def _load_service_account_info() -> dict:
    b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_B64", "").strip()
    if b64:
        raw = base64.b64decode(b64).decode("utf-8")
        return json.loads(raw)

    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw_json:
        return json.loads(raw_json)

    raise RuntimeError("Falta GOOGLE_SERVICE_ACCOUNT_JSON_B64 (recomendado) o GOOGLE_SERVICE_ACCOUNT_JSON")

def get_calendar_service():
    info = _load_service_account_info()
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

def get_calendar_id() -> str:
    cal_id = os.environ.get("GOOGLE_CALENDAR_ID", "").strip()
    if not cal_id:
        raise RuntimeError("Falta GOOGLE_CALENDAR_ID")
    return cal_id

def create_event(summary: str, description: str, start_dt, end_dt) -> str:
    service = get_calendar_service()
    cal_id = get_calendar_id()

    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_dt.isoformat()},
        "end": {"dateTime": end_dt.isoformat()},
    }

    created = service.events().insert(calendarId=cal_id, body=event).execute()
    return created["id"]

def delete_event(event_id: str) -> None:
    if not event_id:
        return
    service = get_calendar_service()
    cal_id = get_calendar_id()
    service.events().delete(calendarId=cal_id, eventId=event_id).execute()
