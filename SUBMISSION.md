# EIRA — StarForge 2026 · VoxForge submission

> EIRA doesn't start from zero — she starts from you.

## Summary (~150 words)

EIRA is an agentic voice companion with real tool access to the user's
environment — calendar write, email, memory, live world state — through a
capability-gated, iteration-bounded native function-calling loop; the tool
layer is MCP-compatible by design and migrating it to MCP servers is the next
architectural step. She reads your week before you speak: a five-rule pattern
engine over wearable and behavioral memory opens the session with one
evidence-backed observation, never a list. Every reply shows its receipts —
which memories were retrieved, which brain answered, what it cost in
milliseconds. Ask her to stop raising a topic and the suppression is data, not
a flag: it survives restarts and filters retrieval, the board, and the spoken
plan. Voice in through the browser's own speech engine, voice out through Rime
Coda, half-duplex with client-side barge-in. Two LLM providers, chained per
model with automatic failover: no turn ever depends on one vendor's uptime.

## What's real and tested tonight

- Bounded agent loop (cap 3, native function calling), smoke-tested 6/6
- Direct-question preemption — time answered mid-plan-flow, no re-monologue
- Live weather (Open-Meteo) and time grounding, all numbers spoken as words
- Deferred-setup onboarding: unconnected calendar/email questions get a
  graceful in-register reply, smoke-tested
- Five-rule pattern engine (sleep, postponement, deflection, HRV, resting HR)
  with receipts; R4 fires live on the seeded burnout trend
- Suppression permanence, forget-vs-complete distinction, tenant isolation —
  all under a 12-case mechanical harness
- Real weekly timetable ingestion; the day planner routes around class hours
- Hedge LLM chain: deprecated-but-serving llama primary, gpt-oss-120b/20b
  tested behind it, Gemini key pool as brain-level fallback

## Designed and gated (code present, needs owner's OAuth consent)

- Google Calendar read/create/move on the user's real calendar
  (Desktop-app OAuth, Testing mode, credentials never leave the machine)
- Gmail read + draft-confirm send (draft spoken aloud, sends only on an
  explicit yes) — designed; executors land with the same consent

## Roadmap (deliberately not tonight)

- MCP-server migration of the tool layer
- Browser control (reliability on free-tier models isn't demo-grade yet)
- ChatGPT memory import ("never start from zero, even on day one")
- Chunked/streaming TTS for sub-second first-audio

## Numbers

- End-to-end spoken turn: p50 ≈ 4.4 s at human pace (e2e test)
- Legacy harness: 12-case mechanical regression — pass rate in final report
- Agent smoke suite: 6/6
- LLM leg: ~0.5–1.1 s single-turn on the Groq chain (throttle-free)
- ~3,700 lines total including tests and scripts; zero agent frameworks
- The harness caught four real defects this week (overlapping HRV baseline,
  cosmetic-only suppression, forget-wired-to-complete, phantom dependencies)
  plus two model-migration regressions tonight — that is what it is for

## Demo script (six beats)

1. "What's the time right now?" — answered instantly, mid-anything
2. "What's the weather like?" — live Open-Meteo, spoken in words
3. Session open: R4 raises recovery with receipts, unprompted
4. Deflect it ("I'll handle it") — receipt-catch, then the warm yield
5. "What should I do first today?" — plan routed around the real timetable
6. "Stop asking about the gym" — and it never comes back

*Edit before submitting.*
