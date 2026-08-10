"""Phase 0: prove Rime synthesis works end to end. Writes out.mp3 next to this script."""
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API_KEY = os.getenv("RIME_API_KEY")
MODEL = os.getenv("RIME_MODEL", "coda")
SPEAKER = os.getenv("RIME_SPEAKER")

TEXT = "Hello boss, EIRA here. All systems warm."


def main() -> None:
    if not API_KEY:
        sys.exit("RIME_API_KEY missing in .env")
    if not SPEAKER:
        sys.exit("RIME_SPEAKER missing in .env, run pick_voice.py first")

    t0 = time.perf_counter()
    resp = requests.post(
        "https://users.rime.ai/v1/rime-tts",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "audio/mp3",
        },
        json={"text": TEXT, "speaker": SPEAKER, "modelId": MODEL},
        timeout=60,
    )
    ms = (time.perf_counter() - t0) * 1000

    if resp.status_code != 200:
        sys.exit(f"FAIL {resp.status_code}: {resp.text[:500]}")

    out = Path(__file__).parent / "out.mp3"
    out.write_bytes(resp.content)
    print(f"OK  model={MODEL} speaker={SPEAKER}  {len(resp.content)} bytes in {ms:.0f} ms -> {out}")
    print("Listen to out.mp3 and confirm the voice fits EIRA before proceeding.")


if __name__ == "__main__":
    main()
