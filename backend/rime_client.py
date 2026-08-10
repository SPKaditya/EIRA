"""Rime Coda over plain HTTP: sanitize_for_speech + speak -> (mp3 bytes, ms)."""
import logging
import os
import re
import time

import requests

logger = logging.getLogger("eira.rime")

RIME_URL = "https://users.rime.ai/v1/rime-tts"

_DASHES = re.compile(r"\s*[—–]\s*")
_CURLY = {"‘": "'", "’": "'", "“": '"', "”": '"', "…": "..."}
_STACKED = re.compile(r"([!?])[!?]+")
_MD = re.compile(r"[*_`#]+")
_TAG = re.compile(r"<[^<>]{1,40}>")
_MULTISPACE = re.compile(r"[ \t]{2,}")
_DIGIT = re.compile(r"\d")


def sanitize_for_speech(text: str) -> str:
    """What the LLM wrote -> what Coda should receive. Digits-to-words is the
    persona's job; we only log a warning when one slips through so the prompt
    gets fixed (never silently patch)."""
    # gpt-oss emits typographic quotes ("What’s"); normalize before the engine
    # sees them so pronunciation never depends on the model's punctuation taste
    for bad, good in _CURLY.items():
        text = text.replace(bad, good)
    text = _DASHES.sub(", ", text)
    text = _STACKED.sub(r"\1", text)
    text = _TAG.sub("", text)
    text = _MD.sub("", text)
    text = _MULTISPACE.sub(" ", text).strip()
    if _DIGIT.search(text):
        logger.warning("digit reached TTS (fix the prompt): %r", text)
    return text


def speak(text: str) -> tuple[bytes, float]:
    """Synthesize sanitized text. Returns (mp3 bytes, latency ms). Raises on HTTP failure."""
    t0 = time.perf_counter()
    resp = requests.post(
        RIME_URL,
        headers={
            "Authorization": f"Bearer {os.environ['RIME_API_KEY']}",
            "Content-Type": "application/json",
            "Accept": "audio/mp3",
        },
        json={
            "text": text,
            "speaker": os.environ["RIME_SPEAKER"],
            "modelId": os.getenv("RIME_MODEL", "coda"),
        },
        timeout=60,
    )
    ms = (time.perf_counter() - t0) * 1000
    resp.raise_for_status()
    return resp.content, ms
