"""Per-turn timing -> JSONL. One line per /chat turn; the UI footer reads the last line."""
import json
import time
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "data" / "latency.jsonl"


def log_turn(**fields) -> dict:
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **fields}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
