# CLAUDE.md — spark-hub

Personal multi-domain monorepo. Each top-level folder is an independent project
with no shared build system. Keep new work inside the right domain folder.

| folder | what it is |
|---|---|
| `EIRA/` | **Active.** Voice companion, StarForge 2026 VoxForge submission. Own git repo, two remotes. |
| `Radar/` | Radar intelligence pipeline (EKF, CNN, browser console). Own CLAUDE.md inside. |
| `ai-ml/` | Hands-On ML practice, scratch work. |
| `web-dev/`, `cpp/`, `dsa/`, `f1-lab/` | Skeletons, largely empty. |

My personal context lives in Spark at `~/spark/` (Windows: `C:\Users\sharm\spark\`).
Read `INDEX.md` there first; it routes to the right note. Do not cascade-load the vault.

---

# EIRA — the file a fresh session needs

**One line:** a voice companion that reads your week before you speak, raises one
thing it noticed with evidence, and drops a subject permanently when you ask.

## Architecture

```
Browser (single static page, push-to-talk, barge-in, audio-reactive orb)
   │ transcript
   ▼
FastAPI  ─► Qdrant Cloud      memory: tasks, preferences, pattern logs, wearables
         ─► Pattern Engine    R1 sleep, R2 postponed, R3 deflection, R4 HRV, R5 resting HR
         ─► LLM               Groq model chain  ⇄  Gemini key pool (auto-failover)
         ─► Rime Coda TTS     plain HTTP synthesis, voice: nadi
         ─► POST /emotion     wav2vec2 speech emotion, OFF the critical path
   ▼
mp3 + receipts + recalled memories + board + day plan + classes
```

No agent framework, no LiveKit, no WebSockets for turns. Request/response,
half-duplex, barge-in handled client side. Roughly 1,500 lines total.

## Key decisions and why

- **Two providers, chained.** Groq walks sibling models (each has its own daily
  token budget) before falling through to a rotating pool of Gemini keys. During
  the build Gemini retired a model mid-session, hit quota, then degraded; no turn
  was ever dropped. Every reply reports which brain answered.
- **Groq leads, not Gemini.** Measured: Groq ~0.5 s, Gemini 4–7 s and prone to
  degradation. With the current persona Groq is *also* warmer. Gemini is insurance.
- **Warmth is prompt engineering.** Rime Coda has no emotion tags; delivery comes
  only from wording and punctuation. Hence `persona.py` is large and specific:
  rationed address terms, named reactive sounds, exact beat placement
  (`Haha, okay... I believe you` reads as affection; `Haha, alright. I believe you.`
  reads as mockery).
- **Numbers never reach TTS as digits.** The persona spells everything;
  `sanitize_for_speech` logs a warning if one slips, so the fix lands in the prompt.
- **Suppression is data, not a flag.** "Stop asking about X" writes a preference
  with `suppressed_topic`, and that topic is filtered from the board, the day plan,
  and vector retrieval. It survives restarts because it is a vector row.
- **Forget ≠ complete.** Two different actions; conflating them leaves the item
  the user asked to erase sitting in memory. The persona says so explicitly.
- **Emotion is confidence-gated and off the critical path.** Clips under 1.5 s or
  confidence under 0.55 return neutral. A confidently wrong "you sound angry" on
  stage is worse than no tone feature.

## Phase status vs `EIRA/finale_master_brief.md` (private, vault only)

| item | state |
|---|---|
| N0.1 model prefetch | done, 13.0 s cold load, 409 ms inference, cached |
| N0.2 eval harness | done, 12/12 green |
| N0.3 wearables v2 + R4/R5 | done, R4 fires live at HRV −24% |
| N0.4 UI scrolling, clock, interim | done, verified at 1100×700 |
| N0.5 timetable ingestion | done, planner routes around class hours |
| A1 emotion endpoint | done, 665 ms warm, `/chat` latency unchanged |
| M1–M4, A2, A3, P1–P3 | **not started**, owner present phases |

## Run commands

```bash
bash scripts/setup_mac.sh          # venv, deps, model cache, wearables, seed
cp .env.example .env               # then fill in the keys

python scripts/gen_wearables.py    # regenerate synthetic health data
python scripts/seed_data.py        # reset demo state, rolls dates to today
uvicorn main:app --app-dir backend --port 8000
```

Verification, all independent:

```bash
python scripts/test_rime.py        # voice synthesis
python scripts/test_qdrant.py      # memory + tenant isolation
python scripts/prefetch_models.py  # emotion model
python scripts/eval_harness.py     # 12-case regression, server must be running
python scripts/e2e_test.py         # scripted conversation at human pace
```

## Gotchas that cost real time

- **Reseed before every demo take.** Testing suppression persists it; the next
  session will correctly refuse to mention that topic.
- **The eval harness throttles itself.** Firing 12 turns back to back at free-tier
  providers inflates latency badly. `--gap` defaults to 2 s. Trust `e2e_test.py`
  (p50 ≈ 4.4 s) for what the demo actually feels like.
- **Groq limits are per model per day.** Exhausting llama does not exhaust the
  chain; it walks to the next model.
- **Killing the server on Windows:** `pkill` does not work. Kill by port.
- **A stale server serves stale code.** uvicorn runs without `--reload`; if a
  change seems to have no effect, the old process is still bound to 8000.
- **`.env` is never committed.** It lives only on disk. `.env.example` is the template.

## Freeze discipline

`main` is always the working demo. Build on `finale`. Merge only when the item's
checkpoint passed **and** the eval harness is green afterward. Anything uncertain
stays on `finale`. If a feature fails its checkpoint twice, park it and revert
rather than debugging indefinitely.

## Remotes

- `origin` → `SPKaditya/eira`, **public submission repo**. Code, README, data,
  scripts, CLAUDE.md. Never planning notes.
- `sparkhub` → `SPKaditya/spark-hub`, **private vault**. Everything, including
  `finale_master_brief.md` and `NIGHT_REPORT.md`, pushed under `eira/*` refs.

Before any public push: grep the diff and history for `AIza`, `gsk_`, `api_key=`,
confirm `.env` is untracked, confirm no absolute user paths.
