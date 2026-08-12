"""N0.5: the weekly class grid.

Loaded from data/timetable.json and exposed three ways:
  today_classes()   the day's blocks, for the context line
  next_class()      the upcoming block, for the header chip and the opener
  busy_hours()      hours the planner must not schedule into

Spoken forms are precomputed so nothing numeric can leak into speech.
Missing or malformed file means the feature is silently off, never an error.
"""
import json
from datetime import date, datetime, time
from pathlib import Path

import clock

DATA = Path(__file__).resolve().parents[1] / "data" / "timetable.json"


def _load() -> dict:
    try:
        return json.loads(DATA.read_text(encoding="utf-8")).get("week", {})
    except (OSError, ValueError):
        return {}


def _hhmm(s: str) -> time | None:
    try:
        h, m = s.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def classes_on(day_name: str) -> list[dict]:
    out = []
    for c in _load().get(day_name, []):
        st, en = _hhmm(c.get("start", "")), _hhmm(c.get("end", ""))
        if not st or not en:
            continue
        out.append({**c, "_start": st, "_end": en,
                    "start_spoken": clock.spoken_clock(st.hour, st.minute)})
    return sorted(out, key=lambda c: c["_start"])


def today_classes(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    return classes_on(now.strftime("%A"))


def next_class(now: datetime | None = None, within_minutes: int | None = None) -> dict | None:
    """The next block today, or the first block tomorrow once today is done."""
    now = now or datetime.now()
    for c in today_classes(now):
        if c["_start"] > now.time():
            if within_minutes is not None:
                delta = (datetime.combine(now.date(), c["_start"]) - now).total_seconds() / 60
                if delta > within_minutes:
                    return None
            return c
    if within_minutes is not None:
        return None
    tomorrow = (now.date().toordinal() + 1)
    nxt = classes_on(date.fromordinal(tomorrow).strftime("%A"))
    if nxt:
        return {**nxt[0], "tomorrow": True}
    return None


def busy_hours(day_name: str) -> set[int]:
    """Whole hours occupied by classes, so the planner can route around them."""
    busy: set[int] = set()
    for c in classes_on(day_name):
        end_h = c["_end"].hour + (1 if c["_end"].minute else 0)
        busy.update(range(c["_start"].hour, max(end_h, c["_start"].hour + 1)))
    return busy


def context_line(now: datetime | None = None) -> str:
    """One line for the LLM context block."""
    now = now or datetime.now()
    todays = today_classes(now)
    if not todays:
        return "TODAY'S CLASSES: none scheduled."
    parts = [f'{c["title"]} at {c["start_spoken"]}' for c in todays]
    line = "TODAY'S CLASSES: " + "; ".join(parts) + "."
    nxt = next_class(now, within_minutes=90)
    if nxt:
        line += f' NEXT UP within the hour and a half: {nxt["title"]} at {nxt["start_spoken"]}.'
    return line
