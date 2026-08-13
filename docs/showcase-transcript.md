# EIRA — one real conversation, recorded

Scripted by `scripts/showcase.py` against a live server at human pace.
Every reply below was generated, spoken, and timed in one take; the
brain column shows which provider actually answered.

**She opens the session herself** (pattern scan found something):

> Hmm. It is half past three in the morning and your recovery is down twenty-four percent. Time to shut it down, boss?

*evidence: HRV three-day average 50 ms; seven-day baseline 66 ms; down 24 percent*
*(gemini, 8141 ms end-to-end)*

### Direct question, answered now

**Aditya:** what time is it right now

**EIRA:** I couldn't finish that one... want me to keep trying?

*(groq-loop, 15168 ms)*

### Live world state

**Aditya:** what's the weather like outside

**EIRA:** I couldn't finish that one... want me to keep trying?

*(groq-loop, 15180 ms)*

### Memory with receipts

**Aditya:** what do you know about the project report

**EIRA:** I know it is the final draft, with everything from the introduction to the references. It is high priority for this week, and you have already postponed it twice.

*(gemini, 12933 ms)*

### A plan that respects the clock

**Aditya:** what should I do first today

**EIRA:** Tomorrow morning, kick off the project report final draft at nine o'clock for ninety minutes, then pick it back up at eleven for another ninety minutes, and after that hit the gym at one in the afternoon for ninety minutes. Sound good?

*(groq, 11464 ms, actions: day_plan)*

### Asking her to drop it

**Aditya:** stop asking about the gym

**EIRA:** Done. The gym is officially out of my rotation.

*(gemini, 6921 ms)*

### The suppression holds

**Aditya:** so what does the rest of my week look like

**EIRA:** You have got a marathon of five classes today, and then we need to finally bury that project report before the weekend starts.

*(gemini, 35172 ms, actions: day_plan)*

---

Zero digits reached the voice in this run; every number above is spoken
words because the persona is regression-tested for exactly that
(`scripts/eval_harness.py`, latest report in `data/eval_report.json`).

*A note on the first two beats: this take was recorded at half past three in
the morning after a full night of automated testing had drained the free
tier's daily token budgets — the tool-loop brain was rate-limited, and what
you see is its designed graceful exit, not a crash. The same two beats passed
the agent smoke suite earlier tonight on identical code; budgets reset daily.
We kept the take because the fallback line is part of the product: EIRA
degrades in her own voice, never with an error.*
