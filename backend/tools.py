"""Action execution: board operations, the adaptive day plan, and memory
audit/delete. Every action EIRA can take is registered in EXECUTORS; anything
not in that table is refused, so the model cannot invent capabilities."""
import logging
import re

import memory

logger = logging.getLogger("eira.tools")


def _norm(s: str) -> str:
    """Loose title key for dedupe: case/punctuation/whitespace insensitive."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def create_task(user_id: str, a: dict) -> dict:
    """Create a task, or quietly reschedule the existing one if it is already on
    the board. Without this the model re-creating a task it already knows about
    (common when he mentions it again) produced duplicate rows in the UI."""
    title = a.get("title", a.get("text", "untitled"))
    key = _norm(title)

    for t in memory.list_all(user_id, kind="task"):
        if _norm(t.get("text", "")) != key:
            continue
        patch = {"status": "todo"}
        if a.get("when"):
            patch["scheduled_for"] = a["when"]
        if a.get("priority"):
            patch["priority"] = a["priority"]
        memory.update_payload(user_id, t["id"], patch)
        return {"type": "create_task", "ok": True, "id": t["id"],
                "title": t["text"], "deduped": True}

    pid = memory.upsert(
        user_id, "task", title,
        {"status": "todo", "priority": a.get("priority", "normal"),
         "scheduled_for": a.get("when"), "postpone_count": 0},
    )
    return {"type": "create_task", "ok": True, "id": pid, "title": title}


def _find_task(user_id: str, title: str) -> dict | None:
    hits = memory.search(user_id, title, limit=1, kind="task")
    return hits[0] if hits else None


def complete_task(user_id: str, a: dict) -> dict:
    t = _find_task(user_id, a.get("title", ""))
    if not t:
        return {"type": "complete_task", "ok": False, "why": "not found"}
    memory.update_payload(user_id, t["id"], {"status": "done"})
    return {"type": "complete_task", "ok": True, "title": t["text"]}


def reschedule_task(user_id: str, a: dict) -> dict:
    t = _find_task(user_id, a.get("title", ""))
    if not t:
        return {"type": "reschedule_task", "ok": False, "why": "not found"}
    memory.update_payload(user_id, t["id"], {"scheduled_for": a.get("when")})
    return {"type": "reschedule_task", "ok": True, "title": t["text"], "when": a.get("when")}


def postpone_task(user_id: str, a: dict) -> dict:
    t = _find_task(user_id, a.get("title", ""))
    if not t:
        return {"type": "postpone_task", "ok": False, "why": "not found"}
    memory.update_payload(user_id, t["id"], {"postpone_count": int(t.get("postpone_count") or 0) + 1})
    return {"type": "postpone_task", "ok": True, "title": t["text"]}


def memory_audit(user_id: str, a: dict) -> dict:
    items = memory.list_all(user_id)
    return {"type": "memory_audit", "ok": True, "count": len(items),
            "items": [{"type": i["type"], "text": i["text"]} for i in items]}


def memory_delete(user_id: str, a: dict) -> dict:
    gone = memory.delete_matching(user_id, a.get("query", ""), limit=1)
    return {"type": "memory_delete", "ok": bool(gone),
            "deleted": [g["text"] for g in gone]}


def day_plan(user_id: str, a: dict) -> dict:
    """Adaptive day plan: order open tasks by what the week actually shows.
    Postponed-and-high-priority first (avoidance costs the most), low-energy
    slots when sleep is short. Clock-aware: never schedules a slot in the past;
    late at night the whole plan rolls to tomorrow and says so."""
    from datetime import datetime

    import clock

    now = datetime.now()
    if clock.is_late(now):
        plan_for, start_clock = "tomorrow", 9
    else:
        plan_for, start_clock = "today", max(9, now.hour + 1)

    tasks = board(user_id)
    logs = memory.list_all(user_id, kind="pattern_log")
    sleeps = sorted(
        [p for p in logs if p.get("metric") == "sleep_hours"],
        key=lambda p: p.get("date", ""),
    )[-3:]
    avg_sleep = sum(float(p["value"]) for p in sleeps) / len(sleeps) if sleeps else None
    low_energy = avg_sleep is not None and avg_sleep < 6.0

    def weight(t: dict) -> tuple:
        pri = {"high": 0, "normal": 1, "low": 2}.get(t.get("priority", "normal"), 1)
        return (-int(t.get("postpone_count") or 0), pri)

    ordered = sorted(tasks, key=weight)
    slots, hour = [], start_clock
    for t in ordered:
        heavy = int(t.get("postpone_count") or 0) >= 2 or t.get("priority") == "high"
        mins = 90 if heavy else 45
        slots.append({
            "title": t["text"],
            "start": f"{hour:02d}:00",
            "start_spoken": clock.spoken_clock(hour),
            "minutes": mins,
            "minutes_spoken": clock.num_words(mins),
            "why": "postponed twice, front-loaded" if int(t.get("postpone_count") or 0) >= 2
                   else ("high priority" if t.get("priority") == "high" else "fits the gap"),
        })
        hour += 2 if heavy else 1
        if low_energy and len(slots) >= 3:
            break

    return {
        "type": "day_plan", "ok": True, "slots": slots,
        "plan_for": plan_for,
        "low_energy": low_energy,
        "avg_sleep": round(avg_sleep, 1) if avg_sleep is not None else None,
    }


EXECUTORS = {
    "day_plan": day_plan,
    "create_task": create_task,
    "complete_task": complete_task,
    "reschedule_task": reschedule_task,
    "postpone_task": postpone_task,
    "memory_audit": memory_audit,
    "memory_delete": memory_delete,
}


def execute(user_id: str, actions: list[dict]) -> list[dict]:
    """Run each action; a failing action never crashes the turn."""
    results = []
    for a in actions or []:
        if not isinstance(a, dict) or not a.get("type"):
            # models occasionally emit {"type": null} or a bare string; refusing
            # it silently is right — a malformed action must not surface as a
            # scary FAIL row in the UI, and must never crash the turn
            logger.warning("dropped malformed action: %r", a)
            continue
        fn = EXECUTORS.get(a["type"])
        if fn is None:
            results.append({"type": a["type"], "ok": False, "why": "unknown action"})
            continue
        try:
            results.append(fn(user_id, a))
        except Exception as exc:
            logger.exception("action failed: %s", a)
            results.append({"type": a.get("type"), "ok": False, "why": str(exc)})
    return results


def board(user_id: str) -> list[dict]:
    """Open tasks for the UI panel and the LLM context."""
    tasks = memory.list_all(user_id, kind="task")
    return [t for t in tasks if t.get("status") != "done"]
