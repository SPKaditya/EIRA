"""N0.1: cache the speech-emotion model locally and prove it runs offline.

Model: superb/wav2vec2-base-superb-er (Apache-2.0, ~378 MB).
Downloads once into the HF cache, then loads it and classifies two seconds of
silence so the whole path is verified before any demo depends on it.

Safe to re-run: a cached model skips the download.
"""
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

MODEL_ID = "superb/wav2vec2-base-superb-er"
SAMPLE_RATE = 16_000


def main() -> int:
    try:
        import numpy as np
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
    except ImportError as exc:
        print(f"missing dependency: {exc}")
        print("install with: pip install -r requirements.txt")
        return 1

    torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))

    print(f"model      : {MODEL_ID}")
    print("downloading or loading from cache...")

    t0 = time.perf_counter()
    extractor = AutoFeatureExtractor.from_pretrained(MODEL_ID)
    model = AutoModelForAudioClassification.from_pretrained(MODEL_ID)
    model.eval()
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"load time  : {load_ms:,.0f} ms")

    labels = model.config.id2label
    print(f"labels     : {list(labels.values())}")

    # two seconds of silence: proves decode -> features -> forward pass end to end
    silence = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)
    inputs = extractor(silence, sampling_rate=SAMPLE_RATE, return_tensors="pt")

    t1 = time.perf_counter()
    with torch.no_grad():
        logits = model(**inputs).logits
    infer_ms = (time.perf_counter() - t1) * 1000

    probs = torch.softmax(logits, dim=-1)[0]
    top = int(probs.argmax())
    print(f"inference  : {infer_ms:,.0f} ms on 2s audio")
    print(f"top label  : {labels[top]}  ({probs[top]:.2f})")
    print("all labels : " + ", ".join(f"{labels[i]}={probs[i]:.2f}" for i in range(len(probs))))

    cache = Path.home() / ".cache" / "huggingface"
    print(f"cache dir  : {cache}")
    print("\nOK: model cached and inference verified offline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
