"""EIRA backend: FastAPI app, /chat spine, static frontend serve.

Run from repo root:  uvicorn main:app --app-dir backend --reload
"""
import base64
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

import clock
import emotion
import latency_log
import llm_client
import memory
import pattern_engine
import rime_client
import timetable
import tools
from persona import FEWSHOT, SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("eira")

app = FastAPI(title="EIRA")

# in-process conversation history: user_id -> deque of {"role", "content"}
HISTORY: dict[str, deque] = defaultdict(lambda: deque(maxlen=12))  # 6 turns = 12 messages

# last voice-tone read per user, consumed by the NEXT turn's context and then
# cleared, so a stale reading can never colour a later conversation
LAST_EMOTION: dict[str, dict] = {}


class ChatIn(BaseModel):
    user_id: str = os.getenv("DEFAULT_USER_ID", "aditya")
    transcript: str
    heard_up_to: str | None = None


VALID_MEMORY_KINDS = {"preference", "task", "correction"}


def _apply_memory_writes(user_id: str, writes: list[dict]) -> None:
    """Persist LLM-proposed memories, dropping malformed ones. The model
    occasionally invents a kind (e.g. 'task_update') or emits an empty text;
    those would surface as blank rows in the memory panel, so they are refused."""
    for w in writes or []:
        kind = (w.get("kind") or "").strip()
        text = (w.get("text") or "").strip()
        if kind not in VALID_MEMORY_KINDS or not text:
            logger.warning("dropped malformed memory_write: %r", w)
            continue
        memory.upsert(user_id, kind, text, w.get("extra"))


def _context_block(user_id: str, transcript: str) -> tuple[str, list[dict]]:
    """Build the retrieved-context block AND return what was retrieved, so the UI
    can show which stored memories shaped this specific reply."""
    # she only ever sees what she is allowed to mention: retrieval can surface a
    # suppressed topic even when the board no longer lists it, so both are filtered
    topics = tools.suppressed_topics(user_id)
    memories = [
        m for m in memory.search(user_id, transcript, limit=6)
        if not any(t and t in m.get("text", "").lower() for t in topics)
    ][:4]
    open_tasks = tools.unsuppressed_board(user_id)
    lines = [clock.current_moment(), timetable.context_line()]

    # voice tone from the PREVIOUS turn, if it was confident. Consumed once so a
    # stale read cannot colour later turns. Deliberately phrased as a hint, not
    # a label to announce: the persona forbids reciting raw labels.
    tone = LAST_EMOTION.pop(user_id, None)
    if tone and not tone.get("low_confidence"):
        lines.append(
            f'VOICE TONE last turn: he sounded {tone["label"]} '
            f'(confidence {tone.get("confidence", 0):.2f}). Do NOT announce this '
            "or name any label. Let it shape your warmth only, and only if his "
            "words agree with it."
        )

    lines.append("RETRIEVED CONTEXT (memories relevant to this turn):")
    lines += [f'- [{m["type"]}] {m["text"]}' for m in memories] or ["- (none)"]
    lines.append("OPEN TASKS:")
    lines += [
        f'- {t["text"]} (priority {t.get("priority","normal")}, postponed {t.get("postpone_count",0)}x'
        + (f', scheduled {t["scheduled_for"]}' if t.get("scheduled_for") else "") + ")"
        for t in open_tasks
    ] or ["- (none)"]
    retrieved = [
        {"type": m["type"], "text": m["text"], "score": round(m["score"], 3)}
        for m in memories
    ]
    return "\n".join(lines), retrieved


@app.post("/chat")
def chat(inp: ChatIn):
    t0 = time.perf_counter()
    user_id = inp.user_id

    msgs: list[dict] = [*FEWSHOT]
    if inp.heard_up_to is not None:
        msgs.append({
            "role": "user",
            "content": "IMPORTANT: user interrupted; they only heard: "
                       f"'{inp.heard_up_to}'. Continue from reality, don't repeat.",
        })
    context, retrieved = _context_block(user_id, inp.transcript)
    msgs.append({"role": "user", "content": context})
    msgs.extend(HISTORY[user_id])
    msgs.append({"role": "user", "content": inp.transcript})

    result, brain, llm_ms = llm_client.chat(SYSTEM_PROMPT, msgs)
    reply = result["reply"]

    executed = tools.execute(user_id, result["actions"])
    _apply_memory_writes(user_id, result["memory_writes"])

    # FIX: the original reply was generated BEFORE the plan existed, so on
    # day_plan turns it comes out vague ("let's tackle the report first...").
    # One fast follow-up call with the computed slots injected produces the
    # turn she actually speaks. Replacement happens before TTS -> spoken once.
    dp = next((x for x in executed if x.get("type") == "day_plan" and x.get("ok")), None)
    if dp and dp.get("slots"):
        try:
            slot_lines = "; ".join(
                f'{s["title"]} at {s["start_spoken"]}, {s["minutes_spoken"]} minutes ({s["why"]})'
                for s in dp["slots"]
            )
            class_note = ""
            if dp.get("classes"):
                names = ", ".join(f'{c["title"]} at {c["start_spoken"]}' for c in dp["classes"])
                class_note = (f" He has classes that day: {names}. The slots are already "
                              "scheduled around them, so mention that you worked around "
                              "his classes rather than listing every class.")
            note = (
                f"{clock.current_moment()}\n"
                f"You just built his plan for {dp['plan_for']}. The slots, in order: "
                f"{slot_lines}."
                + class_note
                + (" He is short on sleep, so the plan was trimmed." if dp.get("low_energy") else "")
                + " Now say it to him: ONE spoken turn, maximum three sentences, every "
                "number as spoken words, walking the plan naturally rather than reciting "
                "a list, ending with exactly one short confirmation question. If the plan "
                "is for tomorrow because it is late now, say that plainly."
            )
            plan_result, plan_brain, plan_ms = llm_client.chat(
                SYSTEM_PROMPT, [{"role": "user", "content": note}]
            )
            if plan_result.get("reply"):
                reply = plan_result["reply"]
                brain, llm_ms = plan_brain, llm_ms + plan_ms
        except Exception:
            logger.exception("day_plan follow-up failed; keeping original reply")

    audio_b64, tts_ms = "", 0.0
    if reply:
        try:
            mp3, tts_ms = rime_client.speak(rime_client.sanitize_for_speech(reply))
            audio_b64 = base64.b64encode(mp3).decode()
        except Exception:
            logger.exception("TTS failed; returning text-only turn")

    HISTORY[user_id].append({"role": "user", "content": inp.transcript})
    HISTORY[user_id].append({"role": "assistant", "content": reply})

    latency = latency_log.log_turn(
        llm_ms=round(llm_ms), tts_ms=round(tts_ms),
        total_ms=round((time.perf_counter() - t0) * 1000), brain=brain,
    )
    return {
        "reply": reply,
        "audio_b64": audio_b64,
        "actions_executed": executed,
        "retrieved": retrieved,
        "board": tools.board(user_id),
        "latency": latency,
    }


@app.get("/session/start")
def session_start(user_id: str = os.getenv("DEFAULT_USER_ID", "aditya")):
    """Fresh session: scan for patterns, open proactively (with receipts) or warmly."""
    t0 = time.perf_counter()
    flag = pattern_engine.session_scan(user_id)

    if flag:
        # Hand the model ONE receipt, not the list. The UI still shows every
        # chip; feeding all of them made her recite the set, which is both
        # un-human and slow to speak.
        headline = flag["evidence"][-1]
        note = (
            f"{clock.current_moment()}\n"
            "SESSION START. Your pattern scan flagged something. Open proactively at "
            "the MENTION/SUGGEST level: state this one fact in spoken words, then one "
            "short suggestion as a question. Do NOT list other numbers. "
            f"The fact: {headline}. Topic: {flag['topic']}."
        )
    else:
        note = (f"{clock.current_moment()}\n"
                "SESSION START. Nothing flagged. Open with a warm, short greeting "
                "that fits the time of day.")

    # Demo-night reversal: Gemini degraded to 46s openers (slow + bad-JSON
    # retries), and "she's waking up" cannot take a minute. The fast chain with
    # few-shot is warm enough; Gemini stays as the automatic fallback only.
    result, brain, llm_ms = llm_client.chat(
        SYSTEM_PROMPT, [*FEWSHOT, {"role": "user", "content": note}]
    )
    reply = result["reply"]
    HISTORY[user_id].clear()
    HISTORY[user_id].append({"role": "assistant", "content": reply})

    audio_b64, tts_ms = "", 0.0
    if reply:
        try:
            mp3, tts_ms = rime_client.speak(rime_client.sanitize_for_speech(reply))
            audio_b64 = base64.b64encode(mp3).decode()
        except Exception:
            logger.exception("TTS failed on session start")

    latency = latency_log.log_turn(
        route="session_start", llm_ms=round(llm_ms), tts_ms=round(tts_ms),
        total_ms=round((time.perf_counter() - t0) * 1000), brain=brain,
    )
    return {
        "reply": reply,
        "audio_b64": audio_b64,
        "evidence": flag["evidence"] if flag else [],
        "flag": {"rule": flag["rule"], "topic": flag["topic"]} if flag else None,
        "board": tools.board(user_id),
        "memories": memory.list_all(user_id, kind="preference")
        + memory.list_all(user_id, kind="correction"),
        "latency": latency,
    }


@app.get("/memories")
def memories(user_id: str = os.getenv("DEFAULT_USER_ID", "aditya")):
    return {"memories": memory.list_all(user_id)}


@app.get("/state")
def state(user_id: str = os.getenv("DEFAULT_USER_ID", "aditya")):
    """Everything the UI can paint before EIRA has finished thinking. Cheap
    (no LLM, no TTS) so the interface is alive in well under a second while
    /session/start is still composing the spoken opener."""
    flag = pattern_engine.session_scan(user_id)
    nxt = timetable.next_class()
    return {
        "board": tools.board(user_id),
        "memories": memory.list_all(user_id),
        "evidence": flag["evidence"] if flag else [],
        "flag": {"rule": flag["rule"], "topic": flag["topic"]} if flag else None,
        "classes": [
            {"title": c["title"], "start": c["start"], "end": c["end"],
             "location": c.get("location", "")}
            for c in timetable.today_classes()
        ],
        "next_class": None if not nxt else {
            "title": nxt["title"], "start": nxt["start"],
            "location": nxt.get("location", ""), "tomorrow": bool(nxt.get("tomorrow")),
        },
    }


@app.get("/wearable")
def wearable():
    """Simulated wearable week for the sleep-pattern card. Single source of
    truth is the same file seed_data.py reads."""
    import json as _json
    return _json.loads((ROOT / "data" / "wearable_sim.json").read_text())


@app.post("/emotion")
async def emotion_endpoint(request: Request, user_id: str = os.getenv("DEFAULT_USER_ID", "aditya")):
    """A1: voice-tone read for the NEXT turn's context. Fire-and-forget from the
    client; it never blocks or delays a spoken reply. A failure here degrades to
    neutral rather than surfacing an error."""
    raw = await request.body()
    if not raw:
        return {"label": "neutral", "low_confidence": True, "reason": "empty body"}
    try:
        result = emotion.classify(raw)
    except Exception:
        logger.exception("emotion classify failed")
        return {"label": "neutral", "low_confidence": True, "reason": "inference error"}

    LAST_EMOTION[user_id] = result
    if not result.get("low_confidence"):
        try:
            memory.upsert(
                user_id, "pattern_log",
                f'voice sounded {result["label"]} during a turn',
                {"metric": "voice_tone", "value": result.get("arousal_proxy", 0.0),
                 "label": result["label"], "confidence": result.get("confidence", 0.0),
                 "date": time.strftime("%Y-%m-%dT%H:%M:%S")},
            )
        except Exception:
            logger.exception("could not log voice tone")
    return result


@app.get("/health")
def health():
    return {"ok": True, "emotion_available": emotion.available()}


app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")
