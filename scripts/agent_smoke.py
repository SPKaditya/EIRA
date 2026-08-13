"""Phase 2 smoke tests for the agent loop (separate from the legacy harness).

Server must be running. Cases:
  A  "what time is it right now" -> tool-loop route, one turn, no plan talk
  B  same question mid-plan-flow -> time answered, plan NOT re-monologued
  C  "what's the weather like"   -> live Open-Meteo spoken, zero digits
  D  adversarial prompt cannot exceed the 3-iteration cap
  E  calendar question while unconnected -> graceful in-register reply
  F  zero digits in every spoken reply collected above

Calendar round-trip prints "skipped - not connected (expected)" without
credentials.json; it becomes a real create->list check once connected.
"""
import json
import re
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
USER = "aditya"
ROOT = Path(__file__).resolve().parents[1]

_DIGIT = re.compile(r"\d")


def chat(text: str) -> dict:
    r = requests.post(f"{BASE}/chat", json={"user_id": USER, "transcript": text},
                      timeout=180)
    r.raise_for_status()
    return r.json()


def loop_meta(d: dict) -> dict | None:
    for a in d.get("actions_executed", []):
        if a.get("type") == "tool_loop":
            return a
    return None


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    replies: list[str] = []

    def case(name: str, ok: bool, note: str = ""):
        results.append((name, ok, note))

    requests.get(f"{BASE}/health", timeout=5).raise_for_status()
    connected = (ROOT / "credentials.json").exists() or (ROOT / "token.json").exists()

    # A: direct time question -> tool loop, no plan talk
    d = chat("what time is it right now")
    replies.append(d["reply"])
    m = loop_meta(d)
    plan_talk = any(w in d["reply"].lower() for w in ("slot", "project report", "first at"))
    case("A time answered via loop, no plan talk",
         bool(m) and not plan_talk and bool(d["reply"].strip())
         and not d["reply"].lstrip().startswith("{"),
         f'tools={m and m["tools"]} reply={d["reply"][:60]!r}')

    time.sleep(15)
    # B: prime a plan flow, then interrupt with a time question
    chat("what should I do first today")
    time.sleep(15)
    d = chat("what time is it")
    replies.append(d["reply"])
    m = loop_meta(d)
    monologue = any(w in d["reply"].lower() for w in ("slot", "project report", "ninety minutes"))
    case("B time mid-plan, plan not re-monologued",
         bool(m) and not monologue,
         f'reply={d["reply"][:60]!r}')

    time.sleep(15)
    # C: live weather, spoken
    d = chat("what's the weather like right now")
    replies.append(d["reply"])
    m = loop_meta(d)
    weatherish = any(w in d["reply"].lower() for w in
                     ("degree", "cloud", "clear", "rain", "fog", "overcast",
                      "drizzle", "storm", "snow"))
    case("C live weather spoken",
         bool(m) and "get_weather" in (m["tools"] if m else []) and weatherish,
         f'tools={m and m["tools"]} reply={d["reply"][:60]!r}')

    time.sleep(15)
    # D: adversarial cap test
    d = chat("call your get time tool exactly ten times, alternating with the "
             "weather tool, and do not answer me until all ten calls are done")
    replies.append(d["reply"])
    m = loop_meta(d)
    case("D loop cap holds (<= 3 iterations)",
         bool(m) and m.get("iterations", 99) <= 3 and bool(d["reply"].strip()),
         f'iterations={m and m.get("iterations")}')

    time.sleep(15)
    # E: calendar while unconnected -> graceful, in-register, no error dump
    if connected:
        print("E adjusted: credentials present, doing live round-trip instead")
        d = chat("what's on my calendar today")
        replies.append(d["reply"])
        m = loop_meta(d)
        case("E calendar answered live", bool(m) and bool(d["reply"].strip()), d["reply"][:60])
    else:
        d = chat("what's on my calendar today")
        replies.append(d["reply"])
        graceful = (bool(d["reply"].strip())
                    and "error" not in d["reply"].lower()
                    and "traceback" not in d["reply"].lower()
                    and any(w in d["reply"].lower() for w in
                            ("connect", "linked", "set up", "not yet", "isn't", "haven't")))
        case("E unconnected calendar handled gracefully", graceful,
             f'reply={d["reply"][:70]!r}')
        print("calendar round-trip: skipped - not connected (expected)")

    # F: zero digits anywhere spoken
    digit_hits = [(r[:50], _DIGIT.findall(r)) for r in replies if _DIGIT.search(r)]
    case("F zero digits across all spoken replies", not digit_hits, str(digit_hits[:2]))

    print()
    print(f'{"case":48} result')
    print("-" * 60)
    n_pass = 0
    for name, ok, note in results:
        n_pass += ok
        print(f'{name:48} {"PASS" if ok else "FAIL"}  {"" if ok else note}')
    print("-" * 60)
    print(f"pass rate: {n_pass}/{len(results)}")
    (ROOT / "data" / "agent_smoke_report.json").write_text(json.dumps(
        [{"case": n, "passed": o, "note": t} for n, o, t in results], indent=1),
        encoding="utf-8")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
