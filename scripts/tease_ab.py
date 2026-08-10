"""Ear test for the tease-pace problem: the clipped phrasing vs the beat
phrasing, each at normal and slightly slowed speed. Listen, pick, set
RIME_SPEED in .env (or leave it unset for normal)."""
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API_KEY = os.getenv("RIME_API_KEY")
SPEAKER = os.getenv("RIME_SPEAKER", "nadi")

VARIANTS = {
    "clipped_normal": ("Haha, alright. I believe you.", None),
    "beat_normal": ("Haha... okay. I believe you.", None),
    "beat_slow": ("Haha... okay. I believe you.", 0.92),
    "beat_slower": ("Haha... okay. I believe you.", 0.85),
}


def main() -> None:
    if not API_KEY:
        sys.exit("RIME_API_KEY missing in .env")
    for name, (text, speed) in VARIANTS.items():
        body = {"text": text, "speaker": SPEAKER, "modelId": "coda"}
        if speed:
            body["speedAlpha"] = speed
        t0 = time.perf_counter()
        r = requests.post(
            "https://users.rime.ai/v1/rime-tts",
            headers={"Authorization": f"Bearer {API_KEY}",
                     "Content-Type": "application/json", "Accept": "audio/mp3"},
            json=body, timeout=60,
        )
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            print(f"{name}: FAIL {r.status_code} {r.text[:120]}")
            continue
        out = Path(__file__).parent / f"tease_{name}.mp3"
        out.write_bytes(r.content)
        print(f"{name:16s} ({speed or 'default'}): {out.name}  {ms:.0f} ms")
    print("\nListen in order. If a slowed one wins, set RIME_SPEED in .env "
          "(e.g. RIME_SPEED=0.92) and restart. Beat phrasing needs no setting, "
          "the persona now writes it automatically.")


if __name__ == "__main__":
    main()
