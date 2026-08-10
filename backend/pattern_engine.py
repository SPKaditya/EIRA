"""Session-start scan -> at most ONE flag (highest severity), with evidence.

Rules (from the brief):
  R1  avg sleep over last 3 logs < 6h          -> severity 3, topic "sleep"
  R2  any task postpone_count >= 2             -> severity 2, topic = task text
  R3  "I'll handle it" logged >= 3 in a week   -> severity 2, topic "deflection"
Suppressed topics (preferences carrying suppressed_topic) are skipped entirely.

Rule functions are pure (lists in, flag-or-None out) so they test offline;
session_scan() is the thin Qdrant-backed wrapper.
"""
import memory

SLEEP_METRIC = "sleep_hours"
DEFLECTION_METRIC = "ill_handle_it"


def rule_sleep(pattern_logs: list[dict]) -> dict | None:
    sleeps = [p for p in pattern_logs if p.get("metric") == SLEEP_METRIC]
    sleeps.sort(key=lambda p: p.get("date", ""))
    last3 = sleeps[-3:]
    if len(last3) < 3:
        return None
    values = [float(p["value"]) for p in last3]
    avg = sum(values) / 3
    if avg >= 6.0:
        return None
    return {
        "rule": "R1",
        "topic": "sleep",
        "severity": 3,
        "evidence": [f"sleep {p.get('date', '?')}: {p['value']} h" for p in last3]
        + [f"three-night average: {avg:.1f} h"],
    }


def rule_postponed(tasks: list[dict]) -> dict | None:
    worst = None
    for t in tasks:
        if t.get("status") == "done":
            continue
        n = int(t.get("postpone_count") or 0)
        if n >= 2 and (worst is None or n > int(worst.get("postpone_count") or 0)):
            worst = t
    if worst is None:
        return None
    return {
        "rule": "R2",
        "topic": worst["text"],
        "severity": 2,
        "evidence": [f"'{worst['text']}' postponed {worst['postpone_count']} times"],
    }


def rule_deflection(pattern_logs: list[dict]) -> dict | None:
    hits = [p for p in pattern_logs if p.get("metric") == DEFLECTION_METRIC]
    if len(hits) < 3:
        return None
    return {
        "rule": "R3",
        "topic": "deflection",
        "severity": 2,
        "evidence": [f"said \"I'll handle it\" {len(hits)} times this week"],
    }


def suppressed_topics(preferences: list[dict]) -> list[str]:
    return [
        str(p["suppressed_topic"]).lower()
        for p in preferences
        if p.get("suppressed_topic")
    ]


def scan(pattern_logs: list[dict], tasks: list[dict], preferences: list[dict]) -> dict | None:
    """Pure core: evaluate all rules, drop suppressed topics, return the single
    highest-severity flag (first wins ties by rule order)."""
    suppressed = suppressed_topics(preferences)
    flags = [
        f
        for f in (rule_sleep(pattern_logs), rule_postponed(tasks), rule_deflection(pattern_logs))
        if f is not None
        and not any(s in f["topic"].lower() or f["topic"].lower() in s for s in suppressed)
    ]
    return max(flags, key=lambda f: f["severity"]) if flags else None


def session_scan(user_id: str) -> dict | None:
    return scan(
        memory.list_all(user_id, kind="pattern_log"),
        memory.list_all(user_id, kind="task"),
        memory.list_all(user_id, kind="preference"),
    )
