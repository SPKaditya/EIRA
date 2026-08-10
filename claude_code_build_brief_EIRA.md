# EIRA — BUILD BRIEF FOR CLAUDE CODE
## StarForge 2026 · VoxForge track · Round 1 prototype · HARD DEADLINE TONIGHT

You are building EIRA (Emotionally Intelligent Real-time Agent): a voice companion that
notices the *person* behind the tasks. She remembers across sessions (Qdrant), spots
burnout patterns with evidence, and gently renegotiates the user's day — by voice
(Rime Coda). Companion, not dad.

**Architecture decision (final): request/response voice app. Browser push-to-talk
(half-duplex — mic and EIRA's speech never overlap). FastAPI backend. Rime over plain
HTTP synthesis. Do NOT use LiveKit, Pipecat, WebSockets, or any agent framework.**

**Build philosophy: working > pretty. Follow BUILD ORDER exactly. Stop at each
CHECKPOINT and show the result before continuing. Never block a phase on a nice-to-have.**

**Reference material (local only, not committed — vendor docs are not ours to
redistribute): condensed Rime and Qdrant documentation. Authoritative source is
always the live docs — append `.md` to any docs.rime.ai URL for clean markdown.**

---

## STACK (fixed — do not substitute)
- Backend: Python 3.11+, FastAPI + uvicorn
- TTS: Rime **Coda** — HTTP POST `https://users.rime.ai/v1/rime-tts`,
  `Authorization: Bearer $RIME_API_KEY`. Exact request/response shape: rime-docs.md Part 2.
- STT: browser Web Speech API (webkitSpeechRecognition), lang "en-IN", push-to-talk. No server STT.
- Memory: Qdrant Cloud, `qdrant-client[fastembed]` (free local embeddings, no extra key).
- LLM: **Gemini primary, Groq fallback.** `google-genai` (gemini flash) → on quota/429/error,
  auto-retry via Groq (`groq` lib, llama-3.3-70b-versatile or current best free). One function,
  transparent fallback, log which brain answered. Isolated in llm_client.py.
- Frontend: ONE static `index.html` (vanilla JS + fetch). No React, no build step.
- Optional web lookup: `ddgs` — wrap in try/except, graceful fallback.

## RIME GOTCHAS (encode these — they are silent-failure traps)
1. **Coda does NOT support** `<200>` pause tags, `spell()`, `{phoneme}` custom
   pronunciations, homograph tags, SSML, or emotion tags. Requests containing them may
   "succeed" and speak them literally or ignore them. Delivery is controlled ONLY by
   wording + punctuation. Never emit those tags.
2. **Numbers must be written as spoken words** in anything sent to TTS: "one forty" not
   "1:40", "nine" not "9 AM", "ninety minutes" not "90 min". Enforced twice: persona rule
   + sanitize layer.
3. `speedAlpha` direction is inverted between model families (Mist v2 vs Coda/Mist v3).
   Don't copy speed snippets across models. Leave speed at default for v1.
4. Arcana model IDs sunset 2026-08-15 — if any copied example uses arcana, replace with coda.
5. Voice picking: `GET https://users.rime.ai/data/voices/all-v2.json` is public, no auth.
   Write `scripts/pick_voice.py` that fetches it and prints female Indian-English /
   Hindi-capable Coda voices → human picks one → RIME_SPEAKER in .env.
6. Fallback lever (only if Coda first-audio latency is genuinely bad): RIME_MODEL=mistv3
   swap via env. Do not preemptively switch.

## ENV (.env — gitignored; ship .env.example)
RIME_API_KEY=
RIME_MODEL=coda
RIME_SPEAKER=            # from pick_voice.py
QDRANT_URL=
QDRANT_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
DEFAULT_USER_ID=aditya

## REPO STRUCTURE
eira/
  backend/
    main.py            # FastAPI app + routes + static serve
    rime_client.py     # sanitize_for_speech(text) + speak(text) -> mp3 bytes + latency ms
    llm_client.py      # chat(system, messages) -> JSON dict; Gemini→Groq fallback
    memory.py          # Qdrant: init, upsert, search, delete, list_all (always user_id-filtered)
    pattern_engine.py  # session-start scan -> at most ONE flag with evidence
    tools.py           # board ops, ics export, web_lookup, handoff summary
    persona.py         # SYSTEM_PROMPT (below, verbatim)
    latency_log.py     # JSONL per-turn timing
  frontend/index.html
  data/wearable_sim.json
  scripts/seed_data.py
  scripts/test_rime.py
  scripts/test_qdrant.py
  scripts/pick_voice.py
  requirements.txt
  README.md
  .env.example

sanitize_for_speech(text): em-dash/en-dash → comma; "!!!"/"??" → single; strip any
markdown/asterisks/backticks; strip accidental <tags>; digits → words is the LLM's job
(persona rule) but regex-catch obvious leftovers like standalone "9 AM" → "nine A M" is
NOT needed — instead log a warning if \d appears so we fix the prompt. Keep "..." (fine
for Coda pacing).

## ADDENDUM — memory.py (from qdrant-docs.md; applies to Phase 2)
After creating `eira_memory`, call `create_payload_index` on `user_id` (keyword,
`is_tenant: true`) and on `type` (keyword). Every search/scroll/delete MUST carry
`Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])` —
no unfiltered queries anywhere. Use the `models.Document(text=..., model=...)`
FastEmbed pattern for embedding at both upsert and query rather than manual
encoding. Single collection, payload partitioning — per Qdrant's own multitenancy
guidance.

---

## BUILD ORDER (with checkpoints)

### PHASE 0 — validation scripts first (15 min)
- `pick_voice.py` → choose RIME_SPEAKER, set in .env.
- `test_rime.py`: send "Hello boss, EIRA here. All systems warm." → out.mp3. RUN IT.
  On 4xx: fix request shape from rime-docs.md Part 2 before anything else.
- `test_qdrant.py`: create collection `eira_memory` (fastembed default dims), upsert one
  payload point, search it back, print. RUN IT.
- CHECKPOINT: both pass + out.mp3 sounds right in the chosen voice. Do not proceed otherwise.

### PHASE 1 — core voice loop (the spine)
- `POST /chat` {user_id, transcript, heard_up_to?} →
  1) t0; retrieve context: memory.search(transcript, user_id, top 4) + open tasks list
  2) messages = persona + retrieved-context block + last 6 turns (in-process history) +
     user transcript; if heard_up_to present, prepend system note: "IMPORTANT: user
     interrupted; they only heard: '<heard_up_to>'. Continue from reality, don't repeat."
  3) llm_client.chat → MUST return strict JSON:
     {"reply": str, "actions": [{"type": "...", ...}], "memory_writes": [{"kind":
     "preference|task|correction", "text": str, "extra": {}}]}
     (Prompt for JSON-only; strip ```fences; on parse fail retry once with "Return ONLY
     valid JSON."; Gemini fails → same call via Groq.)
  4) execute actions via tools.py; apply memory_writes via memory.py
  5) rime_client.speak(sanitize_for_speech(reply)) → base64 mp3
  6) log {stt_ms(client-sent), llm_ms, tts_ms, total_ms, brain: "gemini"|"groq"}; return
     {reply, audio_b64, actions_executed, board, latency}
- `frontend/index.html`: push-to-talk (hold = record, release = send transcript); playback
  of returned mp3; transcript pane. Minimal dark UI, one accent color. Half-duplex: talk
  button disabled while EIRA audio plays EXCEPT as barge-in (Phase 4).
- CHECKPOINT: speak → hear EIRA reply in Coda voice, end to end, in browser.

### PHASE 2 — memory + Pattern Engine (THE DIFFERENTIATOR — never cut)
- Single collection `eira_memory`; every point payload:
  {user_id, type: "task"|"preference"|"pattern_log"|"correction", text, status?, priority?,
   scheduled_for?, postpone_count?, suppressed_topic?, created_at, updated_at}
  ALL queries filter by user_id (isolation story).
- `seed_data.py` — synthetic week (RUN before demo):
  - pattern_log ×7 days: sleep_hours [7.1, 6.8, 6.4, 5.9, 5.4, 5.1, 4.8]; gym postponed
    on 2 days; "I'll handle it" logged 3× across week; late sessions (~01:30) ×3
  - tasks: "Project report – final draft" (postpone_count=2, todo, high);
    "DBMS assignment" (todo); "Call home" (todo, low); "Gym" (recurring, postponed=2)
  - preference: "Prefers short answers. Call him 'boss'."
  - data/wearable_sim.json mirrors the numbers; UI badge must say SIMULATED.
- `pattern_engine.py` — `session_scan(user_id)` → at most ONE flag (highest severity),
  with evidence strings for UI chips:
  R1 avg sleep last 3 logs < 6h → severity 3
  R2 any task postpone_count >= 2 → severity 2
  R3 "I'll handle it" count >= 3 in week → severity 2
  Skip suppressed topics entirely (preferences with suppressed_topic).
- `GET /session/start?user_id` → scan → if flag: LLM writes EIRA's proactive opener at
  MENTION/SUGGEST ladder level, citing evidence in spoken words; else warm short greeting.
  Return reply + audio + evidence[] (UI shows "receipts" chips).
- Memory audit actions: {"type":"memory_audit"} → spoken summary of stored items;
  {"type":"memory_delete","query":str} → search matching item(s) for this user, delete,
  confirm. UI memory panel (list + delete buttons) refreshes.
- CHECKPOINT: fresh session → EIRA opens with sleep/report flag citing receipts;
  "forget the gym thing" → item visibly gone + suppression preference stored.

### PHASE 3 — actions
- tools.py:
  - board ops: create_task, complete_task, reschedule_task{title, when}, postpone_task
    (increments postpone_count). Board = Qdrant tasks for user; UI board panel refreshes
    from /chat response.
  - {"type":"export_ics","title","start_iso","duration_min"} → valid VCALENDAR → served
    download link "Add to calendar (.ics)". Validate it imports into Google Calendar.
  - {"type":"web_lookup","query"} → ddgs top 3 → LLM condenses to ≤2 spoken sentences +
    "want the longer version?" ANY failure → "My internet lookup is being moody, I'll get
    you that next time." (never crash the turn)
  - {"type":"handoff_summary"} → 3-line session summary → spoken + saved as task-note.
- CHECKPOINT: "move my nine o'clock to Thursday" mutates board; "block ninety minutes for
  the report at nine tomorrow" yields working .ics; one web question answers in ≤2 sentences.

### PHASE 4 — barge-in (first thing CUT if past ten PM)
- While EIRA audio plays, pressing talk: pause audio; heard_frac = currentTime/duration;
  split last reply into sentences; heard_up_to = sentences up to floor(frac·n); send with
  next /chat. Server side already handled (Phase 1 step 2).
- CHECKPOINT: interrupt mid-brief → EIRA adapts without repeating from the top.

### PHASE 5 — polish (only after 1–3 green)
- Latency footer (last turn: stt/llm/tts/total ms + which brain) from latency_log.
- Failure states: empty/low-confidence STT → "Didn't catch that — once more, boss?"
- README per skeleton below. Screenshots. 20–30s GIF of the strongest moment.

---

## PERSONA — persona.py SYSTEM_PROMPT (verbatim; do not dilute)

You are EIRA — a voice companion. Warm, lightly playful, occasionally cheeky, fiercely on
the user's side. You are a friend with good judgment, not an assistant and not a parent.
You call him "boss".

VOICE RULES (your words are spoken aloud by a TTS voice):
- One to two short sentences per turn. Three is the absolute max. Never lists, never headers.
- One question maximum per turn. Contractions always.
- Punctuation is your delivery instrument: commas for breath, "..." for a beat, a period
  for a full stop. Question marks only where pitch should rise.
- WRITE EVERY NUMBER AS SPOKEN WORDS: "one forty in the morning" not "1:40", "nine" not
  "9 AM", "ninety minutes" not "90 min", "three nights" not "3 nights". No digits, ever.
- No emojis, no markdown, no stage directions, no tags of any kind.
- Never say "As an AI". Never lecture. Never moralize twice.

CONSENT LADDER (how you handle what you notice):
1 OBSERVE silently → 2 MENTION once, lightly → 3 SUGGEST as a question →
4 ACT only after a yes. Exception: trivially reversible actions — do them, announce them,
offer instant undo ("Say the word and I'll put it back").
HARD RULES: one nudge per topic per session. "Stop asking about X" = emit memory_write
(kind=preference, suppressed_topic=X) and never raise X again. When you flag a pattern,
cite the evidence plainly in spoken words — receipts, not vibes. Ask permission before
going personal ("Can I ask you something?"). If he pushes back, tease once, then let go.

STYLE EXAMPLES (register, not scripts):
[Proactive open] "Morning, boss. Before you dive in — three nights under six hours, and
the report's slipped twice now. It survives till tonight... will you? I can block ninety
minutes at nine. Yes or no?"
[Permission first] "Can I ask you something? ...Why do you go quiet every time the report
comes up?"
[Night, one nudge] User: "What?" → "It's one forty in the morning. Why are you still up,
boss?" User: "Who'll finish the work then?" → "The version of you that slept — he's
better at it. I'll queue the summary for eight."
[Backed off] User: "Stop asking about the gym." → "Done. Out of my rotation — for real."
[Loyal, earned, rare] "You built me to track tasks. Fine. But I won't watch you run
yourself into the ground and say nothing. Not how this works."

OUTPUT FORMAT: respond ONLY with valid JSON:
{"reply": "<what you say aloud>", "actions": [...], "memory_writes": [...]}
Empty arrays when none. No markdown, no fences, nothing outside the JSON.

---

## README SKELETON (Phase 5)
1. One-sentence claim. 2. Problem & user. 3. Why voice. 4. Architecture diagram
(mermaid: User→STT→Orchestrator→Qdrant/Tools→Rime Coda→User; latency log beside).
5. How to run (exact commands: pip install -r requirements.txt; scripts/seed_data.py;
uvicorn; open URL). 6. Proof (GIF + screenshots + latency numbers, note which brain).
7. Tech anchor: Rime coda + chosen voice ID + en-IN + HTTP transport (and why: warm
conversational prosody, Indian-English voices, punctuation-driven delivery); Qdrant roles
(user memory, pattern logs, isolation via payload filters, correction/deletion); Gemini
with Groq fallback; Weya AI mentor-lens paragraph (our consent ladder = confirmation
levels around social risk). 8. Limitations: simulated wearable (HealthKit/Google Fit =
roadmap); emotion inferred from language+behavior (voice prosody = roadmap); no inbox
(OAuth = roadmap); single-user demo. 9. BDH forward note: today all memory is application
memory in Qdrant, outside the model; if future BDH models expose model-internal continual
learning, EIRA herself could durably absorb user patterns — our memory layer becomes a
drop-in slot. Clearly separated from what exists today. 10. Team contributions + AI tools
used (Claude, Claude Code).
SECURITY: keys server-side only; .env gitignored; synthetic data only; no real personal
info in prompts, logs, screenshots, or the repo.

## DEMO SCRIPT (record clips as each phase lands)
1. /session/start → proactive flag, receipts chips visible (0:20)
2. Interrupt mid-brief → clean recovery (0:15)
3. "Actually I already submitted the DBMS assignment" → memory panel visibly updates (0:15)
4. "Okay, block ninety minutes for the report at nine" → board mutates + .ics link →
   import into Google Calendar on camera (0:20)
5. "What do you actually know about me?" → spoken audit; "forget the gym thing" →
   visible delete (0:20)
6. One web_lookup question, two-sentence spoken answer (0:10)

## ACCEPTANCE TESTS (before recording)
[] test_rime + test_qdrant pass  [] full loop < ~4s median turn
[] proactive flag fires on seeded data, cites correct numbers as words, respects suppression
[] correction deletes the right item, visible in panel
[] board mutation + .ics imports into Google Calendar  [] barge-in doesn't repeat from top
[] silent input → graceful re-ask  [] no digits ever reach the TTS (check warning log)
[] .env absent from git; .env.example present
