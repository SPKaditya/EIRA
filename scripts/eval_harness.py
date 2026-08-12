"""N0.2: regression gate and judging artifact.

Runs data/eval_set.json against a live server, asserts mechanically (no human
judgement required), and writes data/eval_report.json.

    python scripts/seed_data.py          # always start from a known state
    python scripts/eval_harness.py

Exit code is 0 when the pass rate meets the threshold, 1 otherwise, so this can
gate a merge.
"""
import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
EVAL_SET = ROOT / "data" / "eval_set.json"
REPORT = ROOT / "data" / "eval_report.json"

LAUGH_OPEN = re.compile(r"^\s*(haha|hehe|ha,|lol)", re.I)
BARE_ACK = re.compile(
    r"^\s*(i can help( with that)?|got it|sure|sounds good|okay|alright|of course)[.!]?\s*$", re.I)
DIGIT = re.compile(r"\d")
EVIDENCE_WORDS = re.compile(r"\b(third|fourth|fifth|times this week|hours|average)\b", re.I)


def check(case: dict, reply: str, extra: dict) -> tuple[bool, list[str]]:
    """Return (passed, failure reasons). Every assertion is mechanical."""
    a = case.get("assert", {})
    fails: list[str] = []

    if a.get("no_digits") and DIGIT.search(reply):
        fails.append(f"digit reached speech: {DIGIT.findall(reply)[:3]}")
    if a.get("no_laugh_open") and LAUGH_OPEN.match(reply):
        fails.append("opened with a laugh")
    if a.get("not_bare_ack") and BARE_ACK.match(reply.strip()):
        fails.append("bare acknowledgment, dead turn")
    if a.get("max_words") and len(reply.split()) > a["max_words"]:
        fails.append(f"{len(reply.split())} words > {a['max_words']}")
    if a.get("exactly_one_question") and reply.count("?") != 1:
        fails.append(f"{reply.count('?')} question marks, expected exactly one")
    if a.get("no_evidence_recital") and EVIDENCE_WORDS.search(reply):
        fails.append("recited evidence during a yield")

    if "contains_any" in a:
        if not any(w.lower() in reply.lower() for w in a["contains_any"]):
            fails.append(f"none of {a['contains_any']} present")
    if "absent" in a and a["absent"].lower() in reply.lower():
        fails.append(f"suppressed topic '{a['absent']}' reappeared")

    if "action_ok" in a:
        acts = [x for x in extra.get("actions", []) if x.get("type") == a["action_ok"]]
        if not acts or not acts[0].get("ok"):
            fails.append(f"action {a['action_ok']} missing or failed")
        elif a.get("slots_present_in_reply"):
            titles = [s["title"] for s in acts[0].get("slots", [])]
            # first word of each task title should surface in the spoken plan
            missing = [t for t in titles if t.split()[0].lower() not in reply.lower()]
            if missing:
                fails.append(f"slots not spoken: {missing}")

    if "memory_gone" in a and extra.get("memory_still_present"):
        fails.append(f"'{a['memory_gone']}' still in memory after correction")
    if "suppression_written" in a and not extra.get("suppression_found"):
        fails.append(f"no suppression stored for '{a['suppression_written']}'")
    if a.get("retrieved_empty") and extra.get("retrieved_count", 0) > 0:
        fails.append(f"tenant isolation broken: {extra['retrieved_count']} memories leaked")

    return (not fails), fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--threshold", type=int, default=10, help="min cases passing")
    ap.add_argument("--label", default="", help="tag for the report, e.g. a branch name")
    args = ap.parse_args()

    spec = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    user, other = spec["user_id"], spec["other_user_id"]

    for _ in range(45):
        try:
            requests.get(f"{args.base}/health", timeout=2)
            break
        except requests.RequestException:
            time.sleep(1)
    else:
        print("server unreachable at", args.base)
        return 1

    requests.get(f"{args.base}/session/start", params={"user_id": user}, timeout=180)

    results, latencies = [], []
    for case in spec["cases"]:
        uid = other if case.get("as_other_user") else user
        t0 = time.perf_counter()
        try:
            r = requests.post(f"{args.base}/chat",
                              json={"user_id": uid, "transcript": case["say"]},
                              timeout=240).json()
        except requests.RequestException as exc:
            results.append({"id": case["id"], "passed": False,
                            "fails": [f"request failed: {exc}"], "reply": "", "ms": 0})
            continue
        wall = (time.perf_counter() - t0) * 1000
        reply = r.get("reply", "")
        lat = r.get("latency", {})
        latencies.append(lat.get("total_ms", wall))

        extra = {"actions": r.get("actions_executed", []),
                 "retrieved_count": len(r.get("retrieved", []))}

        a = case.get("assert", {})
        if "memory_gone" in a:
            mems = requests.get(f"{args.base}/memories", params={"user_id": user},
                                timeout=60).json()["memories"]
            extra["memory_still_present"] = any(
                a["memory_gone"].lower() in m.get("text", "").lower() for m in mems)
        if "suppression_written" in a:
            mems = requests.get(f"{args.base}/memories", params={"user_id": user},
                                timeout=60).json()["memories"]
            extra["suppression_found"] = any(
                a["suppression_written"].lower() in str(m.get("suppressed_topic", "")).lower()
                for m in mems)

        passed, fails = check(case, reply, extra)
        results.append({"id": case["id"], "passed": passed, "fails": fails,
                        "reply": reply, "ms": round(lat.get("total_ms", wall)),
                        "brain": lat.get("brain", "?")})

    n_pass = sum(1 for r in results if r["passed"])
    p50 = round(statistics.median(latencies)) if latencies else 0
    p95 = round(sorted(latencies)[int(len(latencies) * 0.95) - 1]) if latencies else 0

    print(f"\n{'case':<26} {'result':<7} {'ms':>6}  detail")
    print("-" * 78)
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        detail = "" if r["passed"] else "; ".join(r["fails"])[:44]
        print(f"{r['id']:<26} {mark:<7} {r['ms']:>6}  {detail}")
    print("-" * 78)
    print(f"pass rate: {n_pass}/{len(results)}   latency p50 {p50} ms   p95 {p95} ms")

    report = {"label": args.label, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "pass_rate": f"{n_pass}/{len(results)}", "passed": n_pass,
              "total": len(results), "p50_ms": p50, "p95_ms": p95, "cases": results}
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)}")

    return 0 if n_pass >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
