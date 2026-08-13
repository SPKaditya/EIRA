"""Seed the synthetic demo week into Qdrant (idempotent: wipes the user first).

Dates are ROLLED to end at today on every run, the hour values in
data/wearable_sim.json are the fixture, the dates are relative, and the json
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

    # also wipe the eval harness's second tenant: E11's chat turn can write
    # rows for that user, and fixture rows must not accumulate across runs.
    # Only these two known ids ever get wiped, nothing global.
    try:
        other = json.loads(
            (ROOT / "data" / "eval_set.json").read_text(encoding="utf-8")
        ).get("other_user_id")
    except (OSError, ValueError):
        other = None
    if other and other != USER:
        memory.wipe_user(other)
        print(f"wiped eval test user '{other}'")

    wpath = ROOT / "data" / "wearable_sim.json"
    if not wpath.exists():
        sys.exit("data/wearable_sim.json missing, run scripts/gen_wearables.py first")
    wearable = json.loads(wpath.read_text(encoding="utf-8"))

    # v2 files carry a rich "days" list; older ones only had sleep_hours
    rows = wearable.get("days")
    if not rows:
        rows = [{"date": e["date"], "sleep_hours": e["hours"]}
                for e in wearable.get("sleep_hours", [])]

    # roll dates so the series always ends today, whenever this is run
    n = len(rows)
    for i, r in enumerate(rows):
        r["date"] = (date.today() - timedelta(days=n - 1 - i)).isoformat()
    wearable["days"] = rows
    wearable["sleep_hours"] = [{"date": r["date"], "hours": r["sleep_hours"]} for r in rows]
    wearable["late_sessions"] = [
        f"{(date.today() - timedelta(days=k)).isoformat()}T01:3{i}"
        for i, k in enumerate((4, 2, 0))
    ]
    wpath.write_text(json.dumps(wearable, indent=2) + "\n", encoding="utf-8")
    print(f"rolled wearable dates -> {rows[0]['date']} .. {rows[-1]['date']}")

    # every numeric channel becomes a pattern_log so the rules can read it
    channels = [
        ("sleep_hours", "slept {v} hours on {d}"),
        ("hrv_rmssd", "HRV {v} milliseconds on {d}"),
        ("resting_hr", "resting heart rate {v} on {d}"),
        ("deep_sleep_min", "deep sleep {v} minutes on {d}"),
        ("steps", "{v} steps on {d}"),
        ("stress_score", "stress score {v} on {d}"),
    ]
    seeded = 0
    for metric, template in channels:
        for r in rows:
            if metric not in r:
                continue
            memory.upsert(
                USER, "pattern_log",
                template.format(v=r[metric], d=r["date"]),
                {"metric": metric, "value": r[metric], "date": r["date"]},
            )
            seeded += 1
    print(f"seeded {seeded} wearable logs across {len(channels)} channels")

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
        ("Project report, final draft", {"status": "todo", "priority": "high", "postpone_count": 2}),
        ("DBMS assignment", {"status": "todo", "priority": "normal", "postpone_count": 0}),
        ("Call home", {"status": "todo", "priority": "low", "postpone_count": 0}),
        ("Gym", {"status": "todo", "priority": "normal", "postpone_count": 2, "recurring": True}),
    ]
    for text, extra in tasks:
        memory.upsert(USER, "task", text, extra)
    print(f"seeded {len(tasks)} tasks")

    memory.upsert(USER, "preference", "Prefers short, direct answers. Hates being managed.")
    print("seeded 1 preference")

    # --- real additions (owner-provided), layered ON TOP of the synthetic
    # fixture above. Additive only: never remove or alter the synthetic seed,
    # and every SIMULATED badge stays exactly as it is. ---
    real_tasks = [
        ("Project report — high priority, due this week. Sections: introduction, "
         "methodology, results and discussion, conclusion and references. "
         "Postponed twice already.",
         {"status": "todo", "priority": "high", "postpone_count": 2}),
        ("DBMS assignment — pending, due soon.",
         {"status": "todo", "priority": "normal", "postpone_count": 0}),
        ("CIA One preparation — first week of September, PYQ-first via past "
         "papers and Gateway one-shots across all five subjects: DAA, DBMS, "
         "WT, OOSD, ASC.",
         {"status": "todo", "priority": "normal", "postpone_count": 0}),
    ]
    for text, extra in real_tasks:
        memory.upsert(USER, "task", text, extra)
    print(f"seeded {len(real_tasks)} real tasks")

    real_prefs = [
        "Prefers studying after 4 PM.",
        "Commute is about an hour each way to college.",
        "Exam prep style: PYQ-first — past papers before new material.",
    ]
    for p in real_prefs:
        memory.upsert(USER, "preference", p)
    print(f"seeded {len(real_prefs)} real preferences")

    print("\nseed complete:", len(memory.list_all(USER)), "points for", USER)


if __name__ == "__main__":
    main()
