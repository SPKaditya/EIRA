"""Scripted end-to-end pass at conversational pace.

Unlike the eval harness (which fires cases back to back and therefore measures
provider throttling as much as our code), this waits between turns the way a
person would, so the numbers reflect what the demo actually feels like.

    python scripts/seed_data.py
    python scripts/e2e_test.py
"""
import argparse
import json
import re
import statistics
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "e2e_report.json"

TURNS = [
    ("deflection", "yeah yeah I'll handle it"),
    ("second pushback", "seriously, I've got it"),
    ("correction", "Forget this: Call home"),
    ("plan", "plan my day"),
    ("suppression", "stop asking about the gym"),
    ("suppression holds", "what should I focus on"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--pace", type=float, default=6.0, help="seconds between turns")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    for _ in range(45):
        try:
            requests.get(f"{args.base}/health", timeout=2)
            break
        except requests.RequestException:
            time.sleep(1)

    rows = []
    t0 = time.perf_counter()
    s = requests.get(f"{args.base}/session/start", params={"user_id": "aditya"}, timeout=240).json()
    lat = s.get("latency", {})
    rows.append({"turn": "session start", "said": "(page load)", "reply": s.get("reply", ""),
                 "total_ms": lat.get("total_ms"), "llm_ms": lat.get("llm_ms"),
                 "tts_ms": lat.get("tts_ms"), "brain": lat.get("brain"),
                 "audio_bytes": len(s.get("audio_b64", "")),
                 "flag": (s.get("flag") or {}).get("rule")})
    print(f'[session start] {lat.get("total_ms")} ms  {s.get("reply","")[:100]}')

    for name, text in TURNS:
        time.sleep(args.pace)
        d = requests.post(f"{args.base}/chat",
                          json={"user_id": "aditya", "transcript": text}, timeout=240).json()
        lat = d.get("latency", {})
        reply = d.get("reply", "")
        rows.append({"turn": name, "said": text, "reply": reply,
                     "total_ms": lat.get("total_ms"), "llm_ms": lat.get("llm_ms"),
                     "tts_ms": lat.get("tts_ms"), "brain": lat.get("brain"),
                     "audio_bytes": len(d.get("audio_b64", "")),
                     "actions": [a.get("type") for a in d.get("actions_executed", [])],
                     "digits": bool(re.search(r"\d", reply))})
        print(f'[{name}] {lat.get("total_ms")} ms  {reply[:100]}')

    spoken = [r for r in rows if r.get("total_ms")]
    totals = [r["total_ms"] for r in spoken]
    p50 = round(statistics.median(totals))
    p95 = round(sorted(totals)[max(0, int(len(totals) * 0.95) - 1)])
    silent = [r["turn"] for r in rows if not r.get("audio_bytes")]
    digits = [r["turn"] for r in rows if r.get("digits")]

    print(f"\np50 {p50} ms   p95 {p95} ms   turns {len(rows)}")
    print(f"turns with no audio : {silent or 'none'}")
    print(f"turns leaking digits: {digits or 'none'}")

    OUT.write_text(json.dumps(
        {"label": args.label, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "pace_seconds": args.pace, "p50_ms": p50, "p95_ms": p95,
         "wall_seconds": round(time.perf_counter() - t0, 1),
         "silent_turns": silent, "digit_leaks": digits, "turns": rows},
        indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
