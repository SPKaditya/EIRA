# EIRA: Emotionally Intelligent Real-time Agent

**A voice companion that notices the person behind the tasks.**
She remembers across sessions, spots burnout patterns *with evidence*, and
renegotiates your day out loud. Ask her to drop a subject and she drops it for good.

Built for **StarForge 2026 · VoxForge track**.
Voice by **Rime Coda** · memory by **Qdrant** · reasoning by **Groq + Gemini**.

![EIRA opens the session on her own, citing the sleep pattern she found](docs/01-proactive-open.png)

---

## The idea

Most assistants wait to be asked. EIRA opens the conversation, because she already
looked at your week:

> *"Hmm. Your three-night average sleep is five point one hours. Would you try to
> go to bed a little earlier tonight?"*

Nobody prompted that. A pattern engine scanned her stored memory at session start,
found three consecutive nights under six hours, and handed her one piece of
evidence to raise gently, once.

Every claim she makes is backed by a **receipt** shown in the interface. She never
says "you seem tired"; she says "three nights under six hours" and shows you the
row it came from.

## Three things worth looking at

### 1. Memory that visibly changes the answer

The left rail shows **exactly which stored memories were retrieved for the reply
you just heard**, with their similarity scores. This is not a claim that memory
matters. These are the actual vectors that shaped the sentence.

![Recalled memories with similarity scores shape EIRA's answer](docs/02-memory-recall.png)

### 2. A consent ladder she actually obeys

Observe → mention once → suggest → act only on a yes. Deflections get a two-beat
response, never a one-beat brush-off:

| you say | she says |
|---|---|
| "yeah yeah I'll handle it" | *"Mmhm. That's the fourth time this week you've said you'll handle it."* |
| "seriously, I've got it" | *"Haha, okay... I believe you."* |

The receipt comes first, the warm yield only after you push back a second time.
Say **"stop asking about the gym"** and a suppression is written to the vector
store. She will not raise it again in this session or any future one, because the
refusal is *data*, not a flag in memory.

### 3. A plan that respects the clock

Ask her to plan your day and she orders tasks by what your week actually shows:
avoided work front-loaded, the schedule trimmed when you are short on sleep. Ask
after midnight and the plan rolls to tomorrow, and she says so.

![EIRA speaks the plan she just computed](docs/03-day-plan.png)

---

## Architecture

```
Browser  ── push-to-talk (Web Speech API), barge-in, audio-reactive orb
   │  transcript
   ▼
FastAPI ──► Qdrant Cloud     memory: tasks · preferences · pattern logs
        ──► Pattern Engine   R1 sleep · R2 postponed · R3 deflection
        ──► LLM              Groq chain ⇄ Gemini key pool (auto-failover)
        ──► Rime Coda TTS    HTTP synthesis, voice: nadi
   ▼
mp3 + receipts + recalled memories + board + day plan
```

Deliberately no LiveKit, no WebSockets, no agent framework. Request/response and
half-duplex, with barge-in handled client-side. The whole system is about 1,100
lines you can read in one sitting.

**Barge-in:** press the orb while she's talking and she stops, works out how much
of the sentence you actually heard, and continues from there instead of repeating
herself.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env            # add your five keys

python scripts/pick_voice.py    # shortlists Rime voices → set RIME_SPEAKER
python scripts/test_rime.py     # proves TTS works
python scripts/test_qdrant.py   # proves memory + tenant isolation
python scripts/seed_data.py     # loads the synthetic demo week

uvicorn main:app --app-dir backend --port 8000
```

Open <http://127.0.0.1:8000> in Chrome and hold the orb to talk.
Re-run `seed_data.py` to reset the demo (it also rolls the dates so "last night"
is always accurate).

Keys needed: [Rime](https://app.rime.ai/tokens) ·
[Qdrant Cloud](https://cloud.qdrant.io) (free tier) ·
[Groq](https://console.groq.com/keys) ·
[Gemini](https://aistudio.google.com/apikey).

## What she can do (agentic layer)

- **Bounded native tool loop** — OpenAI-style function calling, hard-capped at
  three iterations, graceful spoken exit at the cap. No agent framework; the
  tool layer is MCP-compatible by design and migrating it to MCP servers is the
  next architectural step.
- **Live world grounding** — current time and real Open-Meteo weather, spoken
  with every number as words.
- **Direct-question preemption** — "what time is it?" is answered *now*, even
  mid-plan-flow; a grounded question is never deferred to finish a monologue.
- **Google Calendar, capability-gated** — read, create, and move real events on
  your own calendar once connected (below); without credentials the tools are
  simply absent and she says so gracefully.
- **Gmail, designed and gated** — draft-confirm send flow (she speaks the draft,
  sends only on an explicit yes) ships as design; enable alongside calendar.
- **Honest limits** — Testing-mode OAuth tokens expire weekly; free-tier LLM
  budgets are real (the chain walks sibling models by design: a
  deprecated-but-serving primary with a tested migration path behind it).

## Connect Google (optional — calendar & email tools)

EIRA runs fully without this; connecting takes about two minutes and switches
her calendar/email tools live on your own account:

1. [console.cloud.google.com](https://console.cloud.google.com) → **New Project** (fresh, dedicated).
2. APIs & Services → Library → enable **Google Calendar API** and **Gmail API**.
3. Google Auth Platform → **Branding**: app name "EIRA Local", your email as
   support and developer contact.
4. **Audience**: External, publishing status stays **Testing**, and add your own
   gmail under Test users (skipping this gives Error 403 access_denied).
5. **Data Access** → add scopes `https://www.googleapis.com/auth/calendar` and
   `https://www.googleapis.com/auth/gmail.modify`.
6. **Clients** → Create client → **Desktop app** → download the JSON → save it
   as `credentials.json` in the repo root → restart the server.

First run pops a one-time browser consent (the "unverified app" screen is
expected in Testing mode — continue through it). `token.json` appears after
consent; both files are gitignored and never leave your machine. Honest limit:
Testing-mode refresh tokens expire after seven days, so you re-consent weekly.

## Engineering decisions worth defending

**Memory is multi-tenant by construction.** One Qdrant collection with payload
partitioning, `user_id` indexed as a tenant keyword (`is_tenant=True`) per
Qdrant's own multitenancy guidance. Every search, scroll, payload update and
delete carries the user filter. There is no code path that queries without it.
`test_qdrant.py` asserts a different `user_id` retrieves nothing. Embeddings use
the `models.Document` FastEmbed pattern at both write and query, so there is no
hand-rolled encoding step to drift out of sync.

**Two providers, and the failover is not theoretical.** The Groq chain walks
sibling models (each has its own daily token budget) before falling through to a
rotating pool of Gemini keys; either provider failing is invisible to the user.
During the build Gemini retired a model mid-session, then hit quota, then went
into a high-demand degradation. No turn was ever dropped. Every reply reports
which brain answered, in the status bar.

**Warmth is prompt engineering, not an API feature.** Rime Coda exposes no emotion
tags: delivery comes only from wording and punctuation. So the persona rations
address terms (constant use reads as a verbal tic), names the reactive sounds the
engine renders correctly (`hmm`, `mmhm`, `haha`, `nah`, `alright`), and places the
beat precisely. `Haha, okay... I believe you` lands as affection, where
`Haha, alright. I believe you.` lands as mockery. That distinction was found by
ear and encoded as a rule.

**Nothing numeric reaches the engine as a digit.** The persona writes every number
as spoken words, and `sanitize_for_speech` logs a warning if one slips through, so
the fix lands in the prompt rather than in a regex patch.

**The model cannot invent capabilities.** Every action is registered in an
executor table; anything outside it is refused and logged, so a hallucinated tool
call degrades to a normal turn instead of an error.

## Limitations, stated plainly

- **Wearable data is simulated** (`data/wearable_sim.json`), badged as such in the
  interface. HealthKit / Google Fit integration is roadmap, not built.
- **Emotion is inferred from language and behaviour**, not from voice prosody.
  No acoustic stress analysis is performed, despite what a voice demo might imply.
- **Single-user demo.** The isolation mechanism is real and tested; the demo drives
  one tenant.
- **Speech recognition is the browser's**, so accuracy varies with microphone and
  accent. Chrome only.
- **Latency depends on free-tier providers.** Typical turns land in three to six
  seconds; provider rate limits can occasionally stretch that.

## Security and data handling

API keys are server-side only and never reach the browser. The frontend talks
only to this backend. `.env` is gitignored and `.env.example` ships with empty
placeholders. All demo content is synthetic: no real personal data appears in
prompts, logs, screenshots, or this repository.

## About

Built by [Team Spark](https://github.com/SPKaditya) for StarForge 2026.

EIRA started from a simple frustration: every assistant I had used waited to be
told what to do, and none of them noticed anything. I wanted one that had read
the week before I opened my mouth, that could say something I did not ask to
hear, and that would then let it go when I told it to. Most of the build time
went into the persona rather than the plumbing, because getting a voice to sound
like it means something turned out to be much harder than getting it to speak.


Licensed under the [MIT License](LICENSE).
