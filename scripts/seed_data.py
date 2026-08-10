"""Seed the synthetic demo week into Qdrant (idempotent: wipes the user first).
Numbers mirror data/wearable_sim.json — keep them in sync. RUN BEFORE DEMO."""
import json
import sys
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

    wearable = json.loads((ROOT / "data" / "wearable_sim.json").read_text())

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

    for i, date in enumerate(["2026-08-05", "2026-08-07", "2026-08-09"]):
        memory.upsert(
            USER, "pattern_log", f"said 'I'll handle it' ({date})",
            {"metric": "ill_handle_it", "date": date},
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
