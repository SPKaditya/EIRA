"""Phase 0: A/B ear test. Renders EIRA's stress-test line through both Indian
Coda candidates -> scripts/out_hawa.mp3 and scripts/out_nadi.mp3.

The line goes through the same em-dash sanitization production will apply
(rime_client.sanitize_for_speech), so what you hear is what EIRA will ship.
"""
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

import rime_client  # noqa: E402

API_KEY = os.getenv("RIME_API_KEY")

LINE = (
    "Morning, boss. Three nights under six hours, and the report's slipped twice now... "
    "it survives till tonight, will you? I can block ninety minutes at nine, "
    "say the word, Aditya."
)

CANDIDATES = ["hawa", "nadi"]


def sanitize(text: str) -> str:
    """Same normalisation production applies, so what you hear is what ships."""
    return rime_client.sanitize_for_speech(text)


def main() -> None:
    if not API_KEY:
        sys.exit("RIME_API_KEY missing in .env")

    text = sanitize(LINE)
    print(f"line ({len(text)} chars): {text}\n")

    for speaker in CANDIDATES:
        t0 = time.perf_counter()
        resp = requests.post(
            "https://users.rime.ai/v1/rime-tts",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "Accept": "audio/mp3",
            },
            json={"text": text, "speaker": speaker, "modelId": "coda"},
            timeout=60,
        )
        ms = (time.perf_counter() - t0) * 1000
        if resp.status_code != 200:
            print(f"{speaker}: FAIL {resp.status_code}: {resp.text[:300]}")
            continue
        out = Path(__file__).parent / f"out_{speaker}.mp3"
        out.write_bytes(resp.content)
        print(f"{speaker}: OK  {len(resp.content)} bytes in {ms:.0f} ms -> {out.name}")

    print("\nListen to both. Winner goes in .env as RIME_SPEAKER.")


if __name__ == "__main__":
    main()
