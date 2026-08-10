"""Phase 0: list candidate voices for EIRA from Rime's public voice catalog.

Fetches voice_details.json (public, no auth), filters for Coda voices that fit
EIRA (female, Indian-English / Hindi first, then warm English fallbacks), and
prints a ranked shortlist. A human picks one and sets RIME_SPEAKER in .env.
"""
import json

import requests

VOICE_DETAILS_URL = "https://users.rime.ai/data/voices/voice_details.json"


def indian(v: dict) -> bool:
    blob = f'{v.get("country", "")} {v.get("dialect", "")} {v.get("demographic", "")}'.lower()
    return v.get("lang") == "hin" or " in" in f' {v.get("country", "").lower()}' or "ind" in blob


def main() -> None:
    voices = requests.get(VOICE_DETAILS_URL, timeout=30).json()
    coda = [v for v in voices if v.get("modelId") == "coda"]
    print(f"catalog: {len(voices)} voices total, {len(coda)} on coda\n")

    tier1 = [v for v in coda if v.get("gender") == "Female" and indian(v)]
    tier2 = [v for v in coda if v.get("gender") != "Female" and indian(v)]
    tier3 = [
        v for v in coda
        if v.get("gender") == "Female" and v.get("lang") == "eng" and v.get("flagship")
    ]

    for title, tier in [
        ("TIER 1 — female, Indian (use one of these)", tier1),
        ("TIER 2 — Indian, other gender", tier2),
        ("TIER 3 — fallback: female English flagship voices", tier3[:8]),
    ]:
        print(f"== {title} ==")
        if not tier:
            print("  (none)")
        for v in tier:
            print(
                f'  {v["speaker"]:12s} lang={v.get("lang", "?"):4s} '
                f'country={v.get("country") or "?":4s} age={v.get("age") or "?":12s} '
                f':: {v.get("description", "")[:70]}'
            )
        print()

    print("Pick one and set RIME_SPEAKER in .env")


if __name__ == "__main__":
    main()
