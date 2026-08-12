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
HRV_METRIC = "hrv_rmssd"
RHR_METRIC = "resting_hr"


def _series(logs: list[dict], metric: str) -> list[dict]:
    rows = [p for p in logs if p.get("metric") == metric and p.get("value") is not None]
    rows.sort(key=lambda p: p.get("date", ""))
    return rows


def _avg(rows: list[dict]) -> float:
    return sum(float(r["value"]) for r in rows) / len(rows)


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


def rule_hrv(pattern_logs: list[dict]) -> dict | None:
    """R4: recovery collapsing. Three-day HRV average more than twenty percent
    below the seven-day baseline. Severity 3, because HRV falls before the
    person notices anything."""
    rows = _series(pattern_logs, HRV_METRIC)
    if len(rows) < 10:
        return None
    # baseline must EXCLUDE the recent window, otherwise the collapse being
    # measured is already inside the number it is compared against
    baseline, recent = _avg(rows[-10:-3]), _avg(rows[-3:])
    if baseline <= 0:
        return None
    drop = (baseline - recent) / baseline * 100
    if drop <= 20:
        return None
    return {
        "rule": "R4",
        "topic": "recovery",
        "severity": 3,
        "evidence": [
            f"HRV three-day average {recent:.0f} ms",
            f"seven-day baseline {baseline:.0f} ms",
            f"down {drop:.0f} percent",
        ],
    }


def rule_resting_hr(pattern_logs: list[dict]) -> dict | None:
    """R5: resting heart rate drifting up. Three-day average more than five bpm
    above the seven-day baseline. Severity 2."""
    rows = _series(pattern_logs, RHR_METRIC)
    if len(rows) < 10:
        return None
    baseline, recent = _avg(rows[-10:-3]), _avg(rows[-3:])
    rise = recent - baseline
    if rise <= 5:
        return None
    return {
        "rule": "R5",
        "topic": "resting heart rate",
        "severity": 2,
        "evidence": [
            f"resting heart rate three-day average {recent:.0f} beats per minute",
            f"seven-day baseline {baseline:.0f}",
            f"up {rise:.0f} beats per minute",
        ],
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
    candidates = (
        rule_hrv(pattern_logs),          # R4, severity 3
        rule_sleep(pattern_logs),        # R1, severity 3
        rule_postponed(tasks),           # R2, severity 2
        rule_resting_hr(pattern_logs),   # R5, severity 2
        rule_deflection(pattern_logs),   # R3, severity 2
    )
    flags = [
        f for f in candidates
        if f is not None
        and not any(s in f["topic"].lower() or f["topic"].lower() in s for s in suppressed)
    ]
    # still exactly one flag per session; ties break in the order above, so a
    # physiological signal outranks a behavioural one at equal severity
    return max(flags, key=lambda f: f["severity"]) if flags else None


def session_scan(user_id: str) -> dict | None:
    return scan(
        memory.list_all(user_id, kind="pattern_log"),
        memory.list_all(user_id, kind="task"),
        memory.list_all(user_id, kind="preference"),
    )
