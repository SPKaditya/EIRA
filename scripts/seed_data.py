"""Seed the synthetic demo week into Qdrant (idempotent: wipes the user first).

Dates are ROLLED to end at today on every run — the hour values in
data/wearable_sim.json are the fixture, the dates are relative — and the json
is rewritten with the rolled dates so the UI's sleep chart, the receipts, and
the pattern engine all agree on when "last night" was. RUN BEFORE DEMO."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

import memory  # noqa: E402

USER = "aditya"


def main() -> None:
    memory.wipe_user(USER)
    print(f"wiped user '{USER}'")

    wpath = ROOT / "data" / "wearable_sim.json"
    wearable = json.loads(wpath.read_text())

    # roll all dates so the series ends today
    hours = [e["hours"] for e in wearable["sleep_hours"]]
    days = [date.today() - timedelta(days=len(hours) - 1 - i) for i in range(len(hours))]
    wearable["sleep_hours"] = [
        {"date": d.isoformat(), "hours": h} for d, h in zip(days, hours, strict=True)
    ]
    wearable["late_sessions"] = [
        f"{(date.today() - timedelta(days=k)).isoformat()}T01:3{i}"
        for i, k in enumerate((4, 2, 0))
    ]
    wpath.write_text(json.dumps(wearable, indent=2) + "\n")
    print("rolled wearable dates ->", days[0], "..", days[-1])

    for entry in wearable["sleep_hours"]:
        memory.upsert(
            USER, "pattern_log", f"slept {entry['hours']} hours on {entry['date']}",
            {"metric": "sleep_hours", "value": entry["hours"], "date": entry["date"]},
        )
    print(f"seeded {len(wearable['sleep_hours'])} sleep logs")

    for ts in wearable["late_sessions"]:
        memory.upsert(
            USER, "pattern_log", f"worked late, session at {ts}",
            {"metric": "late_session", "date": ts},
        )
    print(f"seeded {len(wearable['late_sessions'])} late sessions")

    for k in (5, 3, 1):
        d = (date.today() - timedelta(days=k)).isoformat()
        memory.upsert(
            USER, "pattern_log", f"said 'I'll handle it' ({d})",
            {"metric": "ill_handle_it", "date": d},
        )
    print("seeded 3 deflection logs")

    tasks = [
        ("Project report – final draft", {"status": "todo", "priority": "high", "postpone_count": 2}),
        ("DBMS assignment", {"status": "todo", "priority": "normal", "postpone_count": 0}),
        ("Call home", {"status": "todo", "priority": "low", "postpone_count": 0}),
        ("Gym", {"status": "todo", "priority": "normal", "postpone_count": 2, "recurring": True}),
    ]
    for text, extra in tasks:
        memory.upsert(USER, "task", text, extra)
    print(f"seeded {len(tasks)} tasks")

    memory.upsert(USER, "preference", "Prefers short, direct answers. Hates being managed.")
    print("seeded 1 preference")

    print("\nseed complete:", len(memory.list_all(USER)), "points for", USER)


if __name__ == "__main__":
    main()
