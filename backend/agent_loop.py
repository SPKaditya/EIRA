"""Phase 2: bounded agentic tool loop + direct-question preemption.

Native OpenAI-style function calling on Groq (NOT hand-rolled ReAct). The 7
legacy local executors stay on the single-shot JSON path the harness depends
on; ONLY external tools route through here: get_time, get_weather, and the
calendar three when credentials exist. Hard cap 3 iterations; cap exceeded
degrades to a graceful spoken exit, never an error dump.

Tool RESULTS carry spoken forms (words, not digits) so the final reply can obey
the persona's no-digits rule without any model heroics.
"""
import json
import logging
import os
import re
import time

import requests as _requests

import clock
import gcal

logger = logging.getLogger("eira.agent")

# Loop brain decision record, 2026-08-14 night: llama-3.3 (intended primary)
# AND gpt-oss-120b both exhausted their Groq TPD budgets under the night's own
# harness runs before tool-calling quality could be compared — the free tier's
# real ceiling is the daily token budget, not the model. gpt-oss-20b carried
# the smoke suite on a fresh budget. Env-overridable to promote a bigger brain
# on a fresh day; budgets reset on a rolling 24 h window.
LOOP_MODEL = os.getenv("LOOP_MODEL", "openai/gpt-oss-20b")
MAX_ITERATIONS = 3
CAP_EXIT = "I couldn't finish that one... want me to keep trying?"

# ------------------------------------------------------------ direct questions
# Conservative on purpose: time/date/weather/calendar/email question forms only.
# Bare "schedule"/"plan" stays on the legacy day-plan path.
_DIRECT = re.compile(
    r"(what('| i)?s the time|what time is it|time right now|current time"
    r"|what('| i)?s the date|what('| i)?s today('| i)?s date|what day is it"
    r"|weather|forecast|temperature|raining|will it rain"
    r"|my calendar|on the calendar|calendar (today|tomorrow|this week)"
    r"|email|emails|inbox|unread mail)",
    re.IGNORECASE,
)


def is_direct_question(transcript: str) -> bool:
    return bool(_DIRECT.search(transcript or ""))


# ------------------------------------------------------------------- weather
_geo_cache: dict = {}
_WEATHER_CODES = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
    81: "rain showers", 82: "violent rain showers", 95: "a thunderstorm",
    96: "a thunderstorm with hail", 99: "a thunderstorm with hail",
}


def _latlon() -> tuple[float, float, str]:
    place = os.getenv("LOCATION", "Delhi")
    if place in _geo_cache:
        return _geo_cache[place]
    r = _requests.get("https://geocoding-api.open-meteo.com/v1/search",
                      params={"name": place, "count": 1}, timeout=10)
    r.raise_for_status()
    hit = (r.json().get("results") or [{}])[0]
    out = (hit.get("latitude", 28.61), hit.get("longitude", 77.21),
           hit.get("name", place))
    _geo_cache[place] = out
    return out


def _spoken_int(n: int) -> str:
    if n < 0:
        return "minus " + clock.num_words(min(-n, 99))
    return clock.num_words(min(n, 99))


def get_weather() -> dict:
    lat, lon, name = _latlon()
    r = _requests.get("https://api.open-meteo.com/v1/forecast",
                      params={"latitude": lat, "longitude": lon,
                              "current_weather": "true"}, timeout=10)
    r.raise_for_status()
    cw = r.json().get("current_weather", {})
    temp = round(cw.get("temperature", 0))
    cond = _WEATHER_CODES.get(int(cw.get("weathercode", 0)), "unremarkable skies")
    return {
        "place": name,
        "summary_spoken": f"{_spoken_int(temp)} degrees and {cond} in {name}",
        "temperature_spoken": f"{_spoken_int(temp)} degrees",
        "conditions": cond,
    }


# ------------------------------------------------------------------ tool set
def _tool(name: str, desc: str, params: dict | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object",
                       "properties": params or {},
                       "required": list(params or {})}}}


def external_tools() -> list[dict]:
    tools = [
        _tool("get_time", "Current date and time, already in spoken words."),
        _tool("get_weather", "Live current weather with spoken-word numbers."),
    ]
    if gcal.available():
        tools += [
            _tool("list_calendar_events", "List real Google Calendar events.",
                  {"range": {"type": "string", "enum": ["today", "tomorrow", "week"]}}),
            _tool("create_event", "Create a real Google Calendar event.",
                  {"title": {"type": "string"},
                   "start_iso": {"type": "string", "description": "ISO local time, Asia/Kolkata"},
                   "end_iso": {"type": "string", "description": "ISO local time, Asia/Kolkata"}}),
            _tool("move_event", "Move an existing Google Calendar event.",
                  {"event_id": {"type": "string"},
                   "new_start_iso": {"type": "string"}}),
        ]
    return tools


def _run_tool(name: str, args: dict) -> dict:
    if name == "get_time":
        return {"now": clock.current_moment()}
    if name == "get_weather":
        return get_weather()
    if name == "list_calendar_events":
        return gcal.exec_list("aditya", args)
    if name == "create_event":
        return gcal.exec_create("aditya", args)
    if name == "move_event":
        return gcal.exec_move("aditya", args)
    return {"ok": False, "why": f"unknown tool {name}"}


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _unwrap(text: str) -> str:
    """Models sometimes ignore the tool-mode override and emit the persona's
    JSON envelope as their final message. Unwrap it deterministically so raw
    JSON (and the digits inside it) can never reach TTS."""
    text = text.strip()
    if not text.startswith("{"):
        return text
    try:
        d = json.loads(_FENCE.sub("", text).strip())
        if isinstance(d, dict) and isinstance(d.get("reply"), str):
            return d["reply"].strip()
    except json.JSONDecodeError:
        pass
    return text


# --------------------------------------------------------------------- loop
TOOL_MODE_OVERRIDE = (
    "\n\nTOOL MODE: in this conversation you have native function tools; use "
    "them for anything external (time, weather, calendar). IGNORE the JSON "
    "output format entirely here: your final message must be ONLY the plain "
    "spoken sentence or two, in your own register, no JSON, no lists, every "
    "number as spoken words."
)


def run_loop(system: str, messages: list[dict]) -> tuple[str, list[str], str, int]:
    """Returns (reply, tools_used, brain, iterations). Never raises to /chat."""
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    convo = [{"role": "system", "content": system + TOOL_MODE_OVERRIDE}, *messages]
    used: list[str] = []
    nudged = False

    for it in range(1, MAX_ITERATIONS + 1):
        extra = ({"reasoning_effort": "medium", "temperature": 0.6}
                 if LOOP_MODEL.startswith("openai/gpt-oss") else {})
        resp = None
        for attempt in (1, 2):
            try:
                resp = client.chat.completions.create(
                    model=LOOP_MODEL,
                    messages=convo,
                    tools=external_tools(),
                    tool_choice="auto",
                    **extra,
                )
                break
            except Exception as exc:
                # free-tier TPM is ~6k/min and one loop request is ~3.4k tokens:
                # a 429 here is routine, not fatal. Breathe once and retry.
                is_rate = "429" in str(exc) or "rate" in str(exc).lower()
                if attempt == 1 and is_rate:
                    logger.warning("loop 429, backing off 12 s")
                    time.sleep(12)
                    continue
                logger.exception("loop model call failed")
                return CAP_EXIT, used, "groq-loop", it
        if resp is None:
            return CAP_EXIT, used, "groq-loop", it
        msg = resp.choices[0].message

        if not getattr(msg, "tool_calls", None):
            reply = _unwrap(msg.content or "") or CAP_EXIT
            return reply, used, "groq-loop", it

        convo.append({"role": "assistant", "content": msg.content or "",
                      "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                if not nudged:
                    nudged = True
                    convo.append({"role": "tool", "tool_call_id": tc.id, "name": name,
                                  "content": json.dumps({"ok": False,
                                                         "why": "malformed arguments JSON, try again"})})
                    continue
                logger.warning("second malformed tool JSON; degrading gracefully")
                return CAP_EXIT, used, "groq-loop", it
            used.append(name)
            t0 = time.perf_counter()
            try:
                result = _run_tool(name, args)
            except Exception as exc:
                logger.exception("tool %s failed", name)
                result = {"ok": False, "why": str(exc)[:100]}
            logger.info("tool %s in %.0f ms", name, (time.perf_counter() - t0) * 1000)
            convo.append({"role": "tool", "tool_call_id": tc.id, "name": name,
                          "content": json.dumps(result)[:1200]})

    return CAP_EXIT, used, "groq-loop", MAX_ITERATIONS
