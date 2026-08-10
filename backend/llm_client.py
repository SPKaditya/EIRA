"""One chat() for both brains: Gemini primary, Groq fallback, strict-JSON out.

chat(system, messages) -> (dict, brain, ms). messages = [{"role": "user"|"assistant",
"content": str}, ...]. Any Gemini failure (quota, 429, network, bad JSON after retry)
falls through to Groq transparently; the caller learns which brain answered.
"""
import json
import logging
import os
import re
import time

logger = logging.getLogger("eira.llm")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
# Measured against gpt-oss-120b on the FINAL persona + few-shot: llama is warmer
# AND ~4x faster (median 681 ms vs 2965 ms, equal reactive-sound count). The
# earlier terseness was the prompt, not the model — once the persona named the
# sounds and forbade bare acknowledgements, llama carried the register fine.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

RETRY_NUDGE = "Return ONLY valid JSON."


def _parse(text: str) -> dict:
    return json.loads(_FENCE.sub("", text.strip()).strip())


def _gemini_keys() -> list[str]:
    """GEMINI_API_KEY plus any GEMINI_API_KEY_<n>. Scans until a gap so adding a
    key is purely a .env edit — no code change."""
    keys = [os.getenv("GEMINI_API_KEY")]
    n = 2
    while (k := os.getenv(f"GEMINI_API_KEY_{n}")):
        keys.append(k)
        n += 1
    return [k for k in keys if k]


_gemini_key_idx = 0  # sticky: remember which key worked so rotation costs once, not per turn


def _gemini(system: str, messages: list[dict]) -> str:
    global _gemini_key_idx
    from google import genai
    from google.genai import types

    keys = _gemini_keys()
    if not keys:
        raise RuntimeError("no GEMINI_API_KEY configured")

    last_exc: Exception | None = None
    for offset in range(len(keys)):
        idx = (_gemini_key_idx + offset) % len(keys)
        try:
            text = _gemini_call(genai, types, keys[idx], system, messages)
            _gemini_key_idx = idx
            return text
        except Exception as exc:
            # quota/auth failures rotate to the next key; other errors too —
            # a dead retry path costs the same either way
            logger.warning("gemini key #%d failed: %s", idx + 1, str(exc)[:120])
            last_exc = exc
    raise last_exc if last_exc is not None else RuntimeError("gemini: no key attempted")


def _gemini_call(genai, types, api_key: str, system: str, messages: list[dict]) -> str:
    # hard per-call timeout: a degraded Gemini must fail fast and yield to the
    # next key/brain, never hang the voice loop (observed 46s openers without it)
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=12_000),
    )
    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
        ),
    )
    return resp.text


# Groq's free tier caps tokens PER MODEL per day (100k TPD each). Heavy testing
# exhausted llama's budget mid-build, so the chain walks sibling models — each
# with its own budget — before giving up and letting Gemini catch it.
# gpt-oss-120b was the measured warmth runner-up; 8b-instant is the last resort.
GROQ_CHAIN = list(dict.fromkeys([GROQ_MODEL, "openai/gpt-oss-120b", "llama-3.1-8b-instant"]))
_groq_idx = 0  # sticky: remember which model is currently accepting


def _groq(system: str, messages: list[dict]) -> str:
    global _groq_idx
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    last_exc: Exception | None = None
    for offset in range(len(GROQ_CHAIN)):
        idx = (_groq_idx + offset) % len(GROQ_CHAIN)
        try:
            resp = client.chat.completions.create(
                model=GROQ_CHAIN[idx],
                messages=[{"role": "system", "content": system}, *messages],
                response_format={"type": "json_object"},
            )
            _groq_idx = idx
            return resp.choices[0].message.content
        except Exception as exc:
            logger.warning("groq model %s failed: %s", GROQ_CHAIN[idx], str(exc)[:110])
            last_exc = exc
    raise last_exc if last_exc is not None else RuntimeError("groq: no model attempted")


def _try_brain(fn, name: str, system: str, messages: list[dict]) -> dict | None:
    try:
        return _parse(fn(system, messages))
    except json.JSONDecodeError:
        logger.warning("%s returned unparseable JSON, retrying once", name)
        try:
            return _parse(fn(system, [*messages, {"role": "user", "content": RETRY_NUDGE}]))
        except Exception as exc:
            logger.warning("%s retry failed: %s", name, exc)
    except Exception as exc:
        logger.warning("%s failed: %s", name, exc)
    return None


BRAINS = {"gemini": _gemini, "groq": _groq}

# Measured on this persona (same prompts, both brains):
#   groq   ~0.5 s, correct but clipped  -> "Alright. Forget it."
#   gemini ~4-7 s, noticeably warmer    -> "Haha, alright. I believe you, boss."
# So route by what the moment needs rather than picking one globally: the
# proactive opener is the emotional peak and happens once while the page is
# already loading, so it gets the warm brain; live conversational turns get the
# fast one, because there latency IS the experience.
WARM, FAST = "gemini", "groq"


def chat(system: str, messages: list[dict], warm: bool = False) -> tuple[dict, str, float]:
    """Run the turn. warm=True prefers the warmer/slower brain; either way the
    other brain is the automatic fallback, so a dead key never kills a turn."""
    override = os.getenv("LLM_PRIMARY")
    primary = override or (WARM if warm else FAST)
    order = [primary] + [b for b in BRAINS if b != primary]

    t0 = time.perf_counter()
    result, brain = None, order[0]
    for name in order:
        result = _try_brain(BRAINS[name], name, system, messages)
        if result is not None:
            brain = name
            break
    ms = (time.perf_counter() - t0) * 1000
    if result is None:
        raise RuntimeError("both brains failed")
    result.setdefault("reply", "")
    result.setdefault("actions", [])
    result.setdefault("memory_writes", [])
    logger.info("brain=%s in %.0f ms", brain, ms)
    return result, brain, ms
