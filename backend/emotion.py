"""A1: speech-emotion inference, deliberately off the critical path.

superb/wav2vec2-base-superb-er (Apache-2.0) over a resampled 16 kHz mono clip.
Returns a label plus arousal and valence proxies derived from it.

Two guards exist because a confidently wrong "you sound angry" is worse than
saying nothing: clips under 1.5 seconds and confidences under 0.55 both come
back as neutral with low_confidence set. The persona layer is expected to stay
silent on tone in that case.

The model loads lazily on first call, so importing this module costs nothing
and a machine that never hits /emotion never pays the memory.
"""
import io
import logging
import time

logger = logging.getLogger("eira.emotion")

MODEL_ID = "superb/wav2vec2-base-superb-er"
SAMPLE_RATE = 16_000
MIN_SECONDS = 1.5
MIN_CONFIDENCE = 0.55

# label -> (arousal, valence), both roughly -1..1
AFFECT = {
    "ang": (0.9, -0.7),
    "hap": (0.7, 0.8),
    "sad": (-0.6, -0.8),
    "neu": (0.0, 0.0),
}
FRIENDLY = {"ang": "agitated", "hap": "bright", "sad": "flat", "neu": "neutral"}

_model = None
_extractor = None


def available() -> bool:
    try:
        import librosa  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _load():
    global _model, _extractor
    if _model is None:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
        t0 = time.perf_counter()
        _extractor = AutoFeatureExtractor.from_pretrained(MODEL_ID)
        _model = AutoModelForAudioClassification.from_pretrained(MODEL_ID)
        _model.eval()
        logger.info("emotion model loaded in %.0f ms", (time.perf_counter() - t0) * 1000)
    return _extractor, _model


def _neutral(reason: str, ms: float = 0.0) -> dict:
    return {"label": "neutral", "confidence": 0.0, "arousal_proxy": 0.0,
            "valence_proxy": 0.0, "low_confidence": True, "reason": reason,
            "inference_ms": round(ms)}


def classify(audio_bytes: bytes) -> dict:
    """Decode any container ffmpeg/audioread understands, resample, classify."""
    if not available():
        return _neutral("dependencies missing")

    import librosa
    import numpy as np
    import torch

    t0 = time.perf_counter()
    try:
        wav, _ = librosa.load(io.BytesIO(audio_bytes), sr=SAMPLE_RATE, mono=True)
    except Exception as exc:
        logger.warning("decode failed: %s", str(exc)[:120])
        return _neutral("decode failed")

    seconds = len(wav) / SAMPLE_RATE
    if seconds < MIN_SECONDS:
        return _neutral(f"clip too short ({seconds:.1f}s)", (time.perf_counter() - t0) * 1000)
    if not np.isfinite(wav).all() or float(np.abs(wav).max() or 0) < 1e-4:
        return _neutral("silent clip", (time.perf_counter() - t0) * 1000)

    extractor, model = _load()
    inputs = extractor(wav, sampling_rate=SAMPLE_RATE, return_tensors="pt")
    with torch.no_grad():
        probs = torch.softmax(model(**inputs).logits, dim=-1)[0]

    idx = int(probs.argmax())
    raw = model.config.id2label[idx]
    conf = float(probs[idx])
    ms = (time.perf_counter() - t0) * 1000

    if conf < MIN_CONFIDENCE:
        return _neutral(f"low confidence ({conf:.2f} on {raw})", ms)

    arousal, valence = AFFECT.get(raw, (0.0, 0.0))
    return {
        "label": FRIENDLY.get(raw, raw),
        "raw_label": raw,
        "confidence": round(conf, 3),
        "arousal_proxy": arousal,
        "valence_proxy": valence,
        "low_confidence": False,
        "seconds": round(seconds, 2),
        "inference_ms": round(ms),
    }
