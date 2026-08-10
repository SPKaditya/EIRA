# EIRA — Emotionally Intelligent Real-time Agent

A voice companion that notices the person behind the tasks. She remembers across
sessions, spots burnout patterns with evidence, and renegotiates the day out loud.

**StarForge 2026 · VoxForge track**

---

## What she does

Open the page and she speaks first, because she already looked at the week:

> "Hmm. Your sleep dropped to four point eight hours last night. Want to shut it
> down early tonight?"

Every claim she makes is backed by a stored receipt, shown as a chip in the UI.
Tell her to stop and she stops permanently — the suppression is written to memory,
not held in a variable.

## Architecture

```
Browser (push-to-talk, Web Speech API)
   │  transcript
   ▼
FastAPI  ──►  Qdrant Cloud      (memory: tasks, preferences, pattern logs)
   │      ──►  Pattern Engine    (R1 sleep / R2 postponed / R3 deflection)
   │      ──►  LLM (Groq ⇄ Gemini, automatic failover)
   │      ──►  Rime Coda TTS     (HTTP, voice: nadi)
   ▼
mp3 + board + receipts + recalled-memory panel
```

No LiveKit, no WebSockets, no agent framework. Request/response, half-duplex,
with client-side barge-in.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in the five keys
python scripts/pick_voice.py  # shortlist voices -> set RIME_SPEAKER
python scripts/test_rime.py   # proves TTS works
python scripts/test_qdrant.py # proves memory + tenant isolation
python scripts/seed_data.py   # synthetic demo week
uvicorn main:app --app-dir backend --port 8000
```

Open <http://127.0.0.1:8000> in Chrome. Hold the button, speak, release.

## Design decisions worth defending

**Memory is multi-tenant by construction.** One Qdrant collection, payload
partitioning, `user_id` indexed as a tenant keyword (`is_tenant=True`) per
Qdrant's own multitenancy guidance. Every search, scroll, and payload update
carries the user filter — `test_qdrant.py` asserts a different `user_id` sees
nothing. Embeddings go through the `models.Document` FastEmbed pattern at both
write and query, so there is no manual encoding step to drift.

**Two brains, routed by what the moment needs.** Measured on this persona:
Groq answers in well under a second but clipped; Gemini is noticeably warmer and
several times slower. `chat(warm=True)` sends the emotional beats to the warm
brain, live turns to the fast one, and either failing falls through to the other
automatically. This is not theoretical — during the build Gemini's model was
retired mid-session and later hit quota, and the fallback carried both without a
dropped turn.

**Warmth is prompt engineering, not an API feature.** Rime Coda has no emotion
tags: delivery comes only from wording and punctuation. So the persona rations
address terms (they read as a tic when automatic), names the reactive sounds
Rime speaks correctly (`hmm`, `mmhm`, `haha`, `nah`, `alright`), and forbids
reusing a line verbatim. Few-shot exchanges carry the register in-channel because
instructions alone left the fast model terse.

**Nothing numeric reaches the engine as digits.** The persona writes every number
as spoken words, and `sanitize_for_speech` logs a warning if a digit slips
through, so the fix lands in the prompt rather than in a regex patch.

## Limitations, stated plainly

- **Wearable data is simulated.** `data/wearable_sim.json`, badged as such in the
  UI. HealthKit / Google Fit is roadmap.
- **Emotion is inferred from language and behaviour**, not from voice prosody.
- **Single-user demo.** The isolation mechanism is real and tested; the demo
  drives one tenant.
- **STT is the browser's**, so accuracy varies with mic and accent.

## Security

Keys are server-side only. `.env` is gitignored; `.env.example` ships with empty
placeholders. All demo data is synthetic — no real personal information appears
in prompts, logs, screenshots, or this repository.
