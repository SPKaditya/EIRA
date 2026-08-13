"""Google Calendar layer (Phase 1): InstalledAppFlow auth + three executors.

Graceful absence: without credentials.json (and no token.json) available() is
False, the executors never enter the tool table, and everything else runs
unchanged. One consent covers calendar AND gmail.modify so Phase 3 needs no
second browser trip. If SCOPES ever change: delete token.json and re-consent,
otherwise the stale grant fails silently.

Spoken forms are precomputed on every event (same discipline as timetable.py)
so nothing numeric ever has to reach TTS; digits stay for the UI only.
"""
import logging
import time as _time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import clock

ROOT = Path(__file__).resolve().parents[1]
CREDS_FILE = ROOT / "credentials.json"
TOKEN_FILE = ROOT / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]
TZ = ZoneInfo("Asia/Kolkata")
TZ_NAME = "Asia/Kolkata"

logger = logging.getLogger("eira.gcal")

_service = None
_cache: dict = {"at": 0.0, "events": None}
CACHE_SECONDS = 60  # context-block reads per turn must not hammer the API


def available() -> bool:
    return CREDS_FILE.exists() or TOKEN_FILE.exists()


def get_creds():
    """token.json if valid -> refresh if expired -> else browser consent."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            logger.exception("token refresh failed; falling back to consent")
            creds = None
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def service():
    global _service
    if _service is None:
        from googleapiclient.discovery import build
        _service = build("calendar", "v3", credentials=get_creds(),
                         cache_discovery=False)
    return _service


# ------------------------------------------------------------------ helpers
def _parse_when(s: dict) -> datetime | None:
    """Google start/end: dateTime for timed events, date for all-day."""
    if "dateTime" in s:
        return datetime.fromisoformat(s["dateTime"]).astimezone(TZ)
    if "date" in s:
        return datetime.fromisoformat(s["date"] + "T00:00:00").replace(tzinfo=TZ)
    return None


def _spoken_day(dt: datetime, now: datetime) -> str:
    if dt.date() == now.date():
        return "today"
    if dt.date() == (now + timedelta(days=1)).date():
        return "tomorrow"
    return dt.strftime("%A")


def _fmt(ev: dict, now: datetime) -> dict:
    start = _parse_when(ev.get("start", {}))
    end = _parse_when(ev.get("end", {}))
    out = {
        "id": ev.get("id", ""),
        "title": ev.get("summary", "(untitled)"),
        "start": start.strftime("%H:%M") if start else "",
        "end": end.strftime("%H:%M") if end else "",
        "date": start.strftime("%Y-%m-%d") if start else "",
        "start_spoken": (f"{_spoken_day(start, now)} at "
                         f"{clock.spoken_clock(start.hour, start.minute)}") if start else "",
        "location": ev.get("location", ""),
    }
    return out


def _window(rng: str, now: datetime) -> tuple[datetime, datetime]:
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if rng == "tomorrow":
        return day0 + timedelta(days=1), day0 + timedelta(days=2)
    if rng == "week":
        return now, day0 + timedelta(days=7)
    if rng == "today":
        return now, day0 + timedelta(days=1)
    return now, day0 + timedelta(days=7)  # unknown range -> week, never crash


def _list_window(t0: datetime, t1: datetime, now: datetime) -> list[dict]:
    resp = service().events().list(
        calendarId="primary",
        timeMin=t0.isoformat(),
        timeMax=t1.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=10,
        timeZone=TZ_NAME,
    ).execute()
    return [_fmt(e, now) for e in resp.get("items", [])]


def _ensure_iso(s: str, minutes_ahead_default: int = 60) -> str:
    """Trust the model's ISO string but never crash on a bad one."""
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None).isoformat()
    except (ValueError, TypeError):
        fallback = datetime.now(TZ).replace(tzinfo=None) + timedelta(minutes=minutes_ahead_default)
        return fallback.isoformat()


# ------------------------------------------------------------- context feed
def today_events() -> list[dict]:
    """Cached: the context block and /state read this every turn."""
    if _cache["events"] is not None and _time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["events"]
    now = datetime.now(TZ)
    try:
        evs = _list_window(*_window("today", now), now)
    except Exception:
        logger.exception("calendar read failed; context continues without it")
        evs = []
    _cache.update(at=_time.time(), events=evs)
    return evs


def invalidate_cache() -> None:
    _cache.update(at=0.0, events=None)


def next_event() -> dict | None:
    """Next upcoming calendar event today, for the header chip merge."""
    now = datetime.now(TZ)
    for e in today_events():
        if e["start"] and e["start"] > now.strftime("%H:%M"):
            return e
    return None


def context_line() -> str:
    evs = today_events()
    if not evs:
        return "GOOGLE CALENDAR TODAY: nothing scheduled."
    parts = [f'{e["title"]} at {e["start_spoken"]}' for e in evs]
    return "GOOGLE CALENDAR TODAY (live, real): " + "; ".join(parts) + "."


def capability_line() -> str:
    """Announced in context (persona stays frozen): the extra action types the
    model may emit while the calendar is connected."""
    return (
        "EXTRA ACTIONS AVAILABLE (calendar connected): "
        'list_calendar_events{"range": "today"|"tomorrow"|"week"}, '
        'create_event{"title", "start_iso", "end_iso"} (ISO local times, Asia/Kolkata), '
        'move_event{"event_id", "new_start_iso"}. '
        "Speak event times as words; when you create or move an event, confirm "
        "aloud with its spoken time."
    )


# ---------------------------------------------------------------- executors
def exec_list(user_id: str, a: dict) -> dict:
    now = datetime.now(TZ)
    try:
        events = _list_window(*_window((a.get("range") or "today").lower(), now), now)
    except Exception as exc:
        logger.exception("list_calendar_events failed")
        return {"type": "list_calendar_events", "ok": False, "why": str(exc)[:120]}
    return {"type": "list_calendar_events", "ok": True,
            "range": a.get("range", "today"), "events": events}


def exec_create(user_id: str, a: dict) -> dict:
    title = (a.get("title") or "").strip() or "Untitled block"
    start = _ensure_iso(a.get("start_iso", ""))
    end = a.get("end_iso") or ""
    try:
        end = (datetime.fromisoformat(end)).isoformat()
    except (ValueError, TypeError):
        end = (datetime.fromisoformat(start) + timedelta(minutes=60)).isoformat()
    try:
        ev = service().events().insert(calendarId="primary", body={
            "summary": title,
            "start": {"dateTime": start, "timeZone": TZ_NAME},
            "end": {"dateTime": end, "timeZone": TZ_NAME},
        }).execute()
    except Exception as exc:
        logger.exception("create_event failed")
        return {"type": "create_event", "ok": False, "why": str(exc)[:120]}
    invalidate_cache()
    now = datetime.now(TZ)
    return {"type": "create_event", "ok": True, **_fmt(ev, now)}


def exec_move(user_id: str, a: dict) -> dict:
    eid = a.get("event_id") or ""
    if not eid:
        return {"type": "move_event", "ok": False, "why": "no event_id"}
    try:
        ev = service().events().get(calendarId="primary", eventId=eid).execute()
        old_start = _parse_when(ev.get("start", {}))
        old_end = _parse_when(ev.get("end", {}))
        duration = (old_end - old_start) if old_start and old_end else timedelta(minutes=60)
        new_start = datetime.fromisoformat(_ensure_iso(a.get("new_start_iso", "")))
        new_end_raw = a.get("new_end_iso") or ""
        try:
            new_end = datetime.fromisoformat(new_end_raw)
        except (ValueError, TypeError):
            new_end = new_start + duration
        ev = service().events().patch(calendarId="primary", eventId=eid, body={
            "start": {"dateTime": new_start.isoformat(), "timeZone": TZ_NAME},
            "end": {"dateTime": new_end.isoformat(), "timeZone": TZ_NAME},
        }).execute()
    except Exception as exc:
        logger.exception("move_event failed")
        return {"type": "move_event", "ok": False, "why": str(exc)[:120]}
    invalidate_cache()
    now = datetime.now(TZ)
    return {"type": "move_event", "ok": True, **_fmt(ev, now)}
