# Rime TTS — Complete Documentation Reference

> Condensed from all 107 pages of https://docs.rime.ai/ on 2026-08-10, for the EIRA hackathon project.
> Rime is a text-to-speech platform for real-time voice experiences: natural speech generation,
> responsive voice agents, and production deployment (cloud, regional, or on-prem).

## Contents

- **Part 1 — Platform Core**: models (Coda, Mist v3, Mist v2), voice catalog, auth, base URLs, streaming vs WebSockets, latency, regions, errors, compliance, Arcana→Coda migration
- **Part 2 — API Reference**: every endpoint with full parameter tables and examples
- **Part 3 — Text Handling, Pronunciation & Speech Control**: normalization, pauses, spell(), custom pronunciation, homographs, speed, prompting, phonetic alphabet
- **Part 4 — Voice Agents & Platform Integrations**: agent-loop tutorials (Node/Express/FastAPI/Next.js/Vite), LiveKit, Pipecat, Vapi, and other platforms
- **Part 5 — CLI, MCP Server, On-Prem & Platform Admin**: Rime CLI, hosted MCP server, Docker/on-prem deployment, teams, voice cloning

---


# Part 1 — Platform Core: Models, Voices, API Basics, Streaming, Operations

## Platform Overview

- Rime: real-time TTS platform. 500+ voices across model lineup, 9 languages total across platform, instant custom voice cloning.
- Dashboard: `https://app.rime.ai/` — Docs index for LLMs: `https://docs.rime.ai/llms.txt`
- Deployment options: regional cloud API, VPC, on-premises (Docker Compose or Kubernetes). VPC/on-prem keeps audio and text internal.
- Pricing (Starter tier): $0.05 per 1,000 characters; 3,000 free minutes included; 20 concurrent streams limit.
- Developer surfaces: HTTP/WebSocket APIs, CLI (`rime`), dashboard, MCP server (`mcp.rime.ai`), integrations (LiveKit, Pipecat, Vapi, Daily, SignalWire, VideoSDK).
- No official npm/PyPI SDK exists — use raw HTTP/WebSocket.

## Base URLs & Hosts

| Purpose | URL |
|---|---|
| REST API (TTS, voices, coverage) | `https://users.rime.ai` |
| WebSocket API | `wss://users-ws.rime.ai` |
| Text normalization | `https://optimize.rime.ai` |
| US West HTTP (default alias) | `https://users.rime.ai` |
| US West HTTP (explicit, us-west-2) | `https://users-west.rime.ai` |
| US East HTTP (us-east-1) | `https://users-east.rime.ai` |
| US West WS (us-west-2) | `wss://users-ws.rime.ai/ws3` |
| US East WS (us-east-1) | `wss://users-east-ws.rime.ai/ws3` |

Warning: use `users.rime.ai`, NOT `api.rime.ai` (returns 404 for TTS). Regional WS pattern applies to `/ws`, `/ws2`, `/ws3` paths.

## Authentication

- Header (all requests): `Authorization: Bearer YOUR_API_KEY` (capital B).
- Get keys: sign in at `https://app.rime.ai` → API Tokens → create + copy. One token authenticates API, CLI, MCP tools, integrations. Keep server-side.
- CLI: `rime login` stores credentials at `~/.rime/rime.toml`, or `RIME_CLI_API_KEY` env var.
- On-prem: same Bearer header, or `RIME_API_KEY` env var (plus `API_KEY_HEADER` config since 2026-04-24 image).
- Auth failures: `401` with plain-text body `missing headers` (no Authorization header) or `invalid api key` (unrecognized token / missing "Bearer" scheme). Inactive subscription also returns 401 (`invalid subscription`), not 402/403.
- Browser WebSockets cannot set auth headers — connect from a server-side process or proxy through your backend.

## Endpoints

| Method | Path | Host | Purpose |
|---|---|---|---|
| POST | `/v1/rime-tts` | users.rime.ai | Synthesize speech (audio bytes; format via `Accept` header) |
| WSS | `/ws3` | users-ws.rime.ai | Flagship JSON WebSocket — all current/future models |
| WSS | `/ws2` | users-ws.rime.ai | Legacy JSON WebSocket — Mist v1/v2 only |
| WSS | `/ws` | users-ws.rime.ai | Legacy raw-binary WebSocket — Mist v1/v2, Coda |
| GET | `/data/voices/all-v2.json` | users.rime.ai | Voice names by model and language (public) |
| GET | `/data/voices/voice_details.json` | users.rime.ai | Full voice metadata (public) |
| POST | `/oov` | users.rime.ai | Vocabulary coverage — out-of-dictionary words. Body: `{"text": "..."}` |
| POST | `/textnorm` | optimize.rime.ai | Preview normalization of numbers/dates. Body: `{"text": "..."}` |

## Request Parameters (HTTP TTS)

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `text` | string | yes | — | Max 1,000 characters; non-empty |
| `speaker` | string | yes | — | Voice name; must match model/language |
| `modelId` | string | recommended | `mistv3` | `coda` (flagship), `mistv3`, `mistv2`. Unrecognized value silently falls back to Mist v3 — no error. Coda is never the default |
| `lang` | string | no | — | `en`, `es`, `fr`, `pt`, `de`, `ja`, `ar`, `hi` (Mist v3 docs also use `eng`/`spa`/`ger`/`fra`) |
| `samplingRate` | number | no | `24000` | Range 8000–96000. Note: conversion/downsampling occurs for rates other than 22kHz |
| `speedAlpha` | number | no | 1.0 | Coda & Mist v3: >1.0 = faster. Mist v2: <1.0 = faster (inverted) |
| `timeScaleFactor` | number | no | — | Silently clamped to 0.4–2.5 |
| `phonemizeBetweenBrackets` | boolean | no | false | Mist v1/v2 only; accepted but ignored on Mist v3/Coda |
| `noTextNormalization` | boolean | no | false | Skip normalization — only safe if text has no digits/abbreviations/ambiguous punctuation |
| `trainableUtterance` | boolean | no | false | Opt-in for Rime to use data for training |

Output format via `Accept` header: `audio/mpeg`, `audio/wav`, `audio/webm;codecs=opus`, `audio/ogg;codecs=opus`, `audio/L16`, `audio/PCMU`. Unrecognized `Accept` → JSON response with base64 `audioContent` field. Mist v2 additionally offers non-streaming JSON-wrapped MP3/WAV/Opus-OGG/G.711 μ-law.

## Quickstart Example

```python
import json, os, urllib.request
headers = {
    "Accept": "audio/wav",
    "Authorization": f"Bearer {os.environ['RIME_API_KEY']}",
    "Content-Type": "application/json",
}
payload = {"text": "Hello! This is Rime speaking.", "speaker": "celeste", "modelId": "coda"}
req = urllib.request.Request("https://users.rime.ai/v1/rime-tts",
    data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
with urllib.request.urlopen(req) as response, open("output.wav", "wb") as f:
    while chunk := response.read(4096):
        f.write(chunk)
```

curl equivalent:

```bash
curl --request POST --url https://users.rime.ai/v1/rime-tts \
  --header 'Authorization: Bearer YOUR_API_KEY' \
  --header 'Content-Type: application/json' \
  --header 'Accept: audio/mpeg' \
  --data '{"speaker":"astra","text":"hello","modelId":"coda","lang":"en"}'
```

## Models

| Model | `modelId` | Languages | Voices | Latency | Availability |
|---|---|---|---|---|---|
| Coda (flagship) | `coda` | 8: en, ar, fr, de, hi, ja, pt, es | 184 | TTFA P50 96ms / P90 98ms @1 concurrency; P50 150ms / P90 181ms @12; RTF P99 0.33 (H100). Sub-200ms end-to-end cloud | Cloud + on-prem |
| Mist v3 | `mistv3` | 4: en, fr, de, es | 78 | TTFA P50 37ms / P90 56ms @1 concurrency; RTF P99 0.004 (H100). "TTFB well below 100ms" | Cloud + on-prem |
| Mist v2 | `mistv2` | 4: en, fr, de, es | 138 | 175ms median (A10G, 40–50-char sentences) | Cloud + on-prem |
| Mist v1 | — | — | — | — | Deprecated (released April 2022) |
| Arcana | `arcana` / `arcanav2` / `arcanav3` | — | 64 featured | — | Cloud sunset 2026-08-15; on-prem remains |

Feature matrix:

| Feature | Coda | Mist v3 | Mist v2 |
|---|---|---|---|
| Text normalization | yes | yes | yes |
| `spell()` function | yes | yes | yes |
| Speed adjustment | yes | yes | yes |
| Custom pauses | no | yes | yes |
| Inline pronunciation control | no | no | yes |
| Word-level timestamps | yes (en/es only) | — | — |

Selection: Coda = default for new apps, highest voice quality. Mist v3 = lowest latency or custom pauses. Mist v2 = inline pronunciation control. Requests without `modelId` default to Mist v3.

## Voices

- Organized by model and language; each Coda voice serves exactly one language — pairing a voice with a different `lang` is unsupported. Five Mist v3 voices are multi-language; the rest are language-specific.
- Coda dashboard style categories: Professional, Formal, Casual, Energetic.
- Machine-readable catalogs (public, dynamically updated): `GET https://users.rime.ai/data/voices/all-v2.json` (names by model/language), `GET .../data/voices/voice_details.json` (demographics/metadata: gender, age range, accent/origin, tone/energy/formality descriptors).
- Coda metadata fields `dialect`, `demographic`, `genre`, `styles` populated for only about one-third to one-half of voices.

Coda (184 total): English 121 (16 featured), Spanish 25, Japanese 10, Portuguese 8, German 7, Arabic 6, French 5, Hindi 2.
Example Coda voices: `astra` (F, young adult, US en), `bancroft` (M, elder, US en), `beatty` (M, young adult, US en), `clementine` (F, young adult, US en), `marlu` (M, adult, AU en), `celeste` (en), `amanecer` (F, adult, CO es), `celestino` (M, young adult, MX es), `akari` (F, adult, JP ja), `baltasar` (F, adult, BR pt), `aura` (F, adult, DE de).

Mist v3 (78 total): English 62 (16 featured), Spanish 12 (3 featured), German 5, French 4. Language codes documented as `eng`, `spa`, `ger`, `fra`.
Example Mist v3 voices: `astra` (en F), `sirius` (en M), `estelle` (en F, Southern), `talon` (en M), `cove` (en), `luna` (en F), `isa` (es F, MX), `pola` (es F, DO), `amalia` (de F), `klaus` (de M), `juliette` (fr F), `simone` (fr F).

## HTTP Streaming

- Same endpoint: `POST https://users.rime.ai/v1/rime-tts` — response streams as generated; consume incrementally instead of buffering.
- Telephony: request `Accept: audio/PCMU` with `samplingRate: 8000` for native 8kHz μ-law synthesis without transcoding.

```python
import os, requests
with requests.post(
    "https://users.rime.ai/v1/rime-tts",
    headers={"Authorization": f"Bearer {os.environ['RIME_API_KEY']}",
             "Accept": "audio/mpeg", "Content-Type": "application/json"},
    json={"text": "Streaming audio from Rime, as it is generated.",
          "modelId": "coda", "speaker": "astra", "lang": "en"},
    stream=True,
) as response:
    for chunk in response.iter_content(chunk_size=4096):
        play_or_buffer(chunk)  # consume incrementally
```

## WebSockets

Connection: synthesis args as query parameters — `wss://users-ws.rime.ai/ws3?speaker=<voice>&modelId=<model>&audioFormat=<fmt>&lang=<lang>&segment=<mode>`. Auth via `Authorization: Bearer ...` connection header. Set `modelId` explicitly for `/ws3`.

| Endpoint | Format | Models | Timestamps | Context IDs | TTFB optimization |
|---|---|---|---|---|---|
| `/ws3` (flagship) | JSON, base64 audio chunks | All current/future (Coda, Mist v1/v2/v3) | yes | yes | yes |
| `/ws2` (legacy) | JSON, base64 audio chunks | Mist v1/v2 | yes | yes | no |
| `/ws` (legacy) | Raw binary audio | Mist v1/v2, Coda | no | no | no |

WS-only parameters: `audioFormat` (`mp3`, `mulaw`, `pcm`), `segment` (`bySentence` default, `immediate`, `never`).

Client → server messages:

```json
{ "text": "Hello, how can I help you today?", "contextId": "turn-001" }
{ "operation": "flush" }   // synthesize buffer immediately
{ "operation": "clear" }   // discard buffer without synthesis (interruption/barge-in)
{ "operation": "eos" }     // synthesize remaining buffer, emit done, close connection
```

Server → client events: `chunk` (base64 audio on /ws3 and /ws2), `timestamps`, `done`, `error`.

```typescript
type TimestampsEvent = {
  type: "timestamps",
  word_timestamps: { words: string[], start: number[], end: number[] },
  contextId: string | null,
}
type DoneEvent = { type: "done", contextId: string | null }
```

Timestamps are emitted only for English/Spanish (or when `lang` omitted); the other Coda languages send `chunk`/`done` without `timestamps` and without erroring — never block playback waiting on them.

## WebSocket Segmentation (`segment`)

Applies to `/ws3` and `/ws2`; not applicable to `/ws`. Default: `bySentence`.

| Mode | Behavior | Use when |
|---|---|---|
| `never` (recommended for production voice agents) | Never auto-synthesizes; accumulates all tokens until client sends `flush`. One `done` per flush; `eos` flushes the remainder. Interrupt with `clear` | Conversational AI — client controls utterance boundaries |
| `bySentence` (default) | Buffers tokens; synthesizes at sentence/phrase boundaries (`.`, `?`, `!`) when idle. Decimals, abbreviations, mid-sentence ellipses can trigger early synthesis (e.g. `"2."` in `"2.5ml"`) | Clean sentence-structured prose without numbers/abbreviations |
| `immediate` | Synthesizes as soon as text arrives if pipeline idle; tokens arriving during synthesis accumulate and synthesize jointly | Pre-segmented utterances; client handles phrase boundaries |

One `done` event per synthesis run in all modes. Client must send well-formed, concatenable tokens with proper spacing/punctuation.

## Latency

Model benchmarks (single Lambda H100 SXM): see Models table above. Self-hosted Coda: sub-100ms model latency on the GPU engine; cloud adds 25–50ms network RTT (continental US). Cloud API: sub-200ms end-to-end under typical conditions.

Network RTT by route:

| Origin | → US East | → US West |
|---|---|---|
| East Coast | 5–25 ms | 60–85 ms |
| Midwest/South | 25–55 ms | 35–65 ms |
| West Coast | 60–85 ms | 5–25 ms |

Same AWS region baseline: 1–10 ms; coast-to-coast physical floor ~60 ms; >90 ms suggests suboptimal routing.

Optimization checklist:
1. Use Mist v3 for lowest cloud TTFA; Coda when quality outweighs latency.
2. Consume responses as a stream; start playback from first bytes.
3. Route to the nearest regional endpoint (East traffic → US East, West → US West).
4. Request only needed audio — telephony should request 8kHz directly (smaller payloads offset the resampling cost vs. native 22kHz).
5. `noTextNormalization` only for already-normalized text.
6. Reuse WebSocket connections; do not open one per utterance.
7. Measure with `rime speedtest` (CLI TTFB tool against each endpoint).

## Errors

HTTP failures return a **plain-text body, not JSON**. No request ID exists in responses.

| Status | Body examples | Cause | Retry? |
|---|---|---|---|
| 400 | validation text | Missing/empty body; `text` missing/empty/>1,000 chars; missing `speaker`; bad `lang`/`audioFormat` type; unsupported language for model | Never — identical failure |
| 401 | `missing headers`, `invalid api key`, `empty apikey`, `invalid subscription` | No auth header; bad key; unexpanded shell variable; billing state (arrives as 401, not 402/403) | Never |
| 403 | `access forbidden` | Valid credential, account lacks endpoint access | Never |
| 429 | `Currently at websocket limit` | Connections opened too rapidly; account-wide, limit unpublished | Back off connection attempts, reuse connections |
| 500 | `internal error`, `Database error` | Server failure | Exponential backoff + jitter, capped |
| 502 | `text normalization engine error` | Server failure | Exponential backoff + jitter |

- Unsupported `speaker`/`modelId`/`lang` combinations are NOT always rejected — validate against the voice catalog before shipping. A typo'd `modelId` (e.g. `codaa`) silently serves Mist v3 audio.
- WebSocket errors: upgrade failure → HTTP status + plain-text body; open-socket failure → close code `1011` with reason text (often prefixed with an HTTP-equivalent status). `/ws` raw endpoint emits no structured errors.
- Billing: retries are billed as new synthesis — chunk long text by sentences and resume from the last successful chunk.

## Troubleshooting Quick Table

| Symptom | Cause | Fix |
|---|---|---|
| File won't play | Missing/unrecognized `Accept`; error body saved as audio | Check file starts with `RIFF`, not `{` (`head -c 4 output.wav`) |
| Zero-byte file | Request never completed | Confirm URL is exactly `https://users.rime.ai/v1/rime-tts`; check TLS/redirects |
| Wrong voice | Unsupported speaker/model/lang combo or `modelId` typo (silent Mist v3 fallback) | Verify against catalog; Coda voices are one-language |
| Speed ignored | `timeScaleFactor` silently clamped 0.4–2.5; `speedAlpha` inverted on Mist v2 | Use correct param and direction per model |
| Pronunciation ignored | `phonemizeBetweenBrackets` is Mist v1/v2 only | Match feature to model |
| No timestamps | Only en/es emit them | Don't block on timestamp events |
| Close mid-utterance | Server-side 1011 | Log full close reason; retriable if no audio arrived |
| Choppy audio under load | Wrong region | Use nearest regional endpoint |

Wrapped integrations (LiveKit, Pipecat, Vapi, CLI, MCP): reproduce with raw curl using identical `speaker`/`modelId`/`lang`/`Accept` to isolate API vs. integration. Support: `support@rime.ai` with UTC timestamp, endpoint+region, exact params, full status/body or close code+reason, and whether audio arrived.

## Privacy & Compliance

- SOC 2 Type II certified (May 2025); HIPAA compliant (February 2024); BAA and MSA available on request via `support@rime.ai`; compliance reports by email request.
- Default data collection: character counts only. Customer data never used for training unless explicitly opted in via `trainableUtterance=true`.
- VPC/on-prem deployment keeps audio and text entirely internal.
- Docs do not specify GDPR status, retention periods, or residency regions.

## Arcana Sunset & Migration to Coda

- **Cloud Arcana requests switch to Coda on August 15, 2026 at 12:00 UTC.** Affects `modelId` values `arcana`, `arcanav2`, `arcanav3` (cloud only; on-prem Arcana images unaffected). Requests omitting `modelId` continue on Mist v3.
- Migration = change `modelId` to `coda`; endpoints, methods, and parameter names (`text`, `speaker`, `modelId`, `lang`, `samplingRate`, `timeScaleFactor`) are all unchanged. `speedAlpha` direction identical (>1.0 = faster).
- Voice coverage: Coda serves 56 of Arcana's 64 featured voices (87%). Hindi: Arcana `anaya`/`anil`/`arya` → Coda `nadi`/`taru`. Shared voice names still sound different (separately trained models). Sinhala stays on on-prem Arcana only.
- After the cutoff, unmigrated requests succeed silently on Coda — audible difference is the only indicator. No response header names the serving model; verify by config audit, not response inspection.
- Checklist: scan code/config/env for all three Arcana IDs; verify each `speaker` exists in Coda for its `lang`; test every language and every transport (HTTP, `/ws3`, `/ws`).

```bash
# Before/after comparison
curl -X POST https://users.rime.ai/v1/rime-tts \
  -H "Authorization: Bearer $RIME_API_KEY" -H "Content-Type: application/json" \
  -H "Accept: audio/wav" \
  -d '{"text":"Thanks for calling. Can I get your account number?","speaker":"celeste","modelId":"coda","lang":"eng"}' \
  --output after.wav
```

## Changelog Highlights (10 most recent/significant)

1. **2026-08-04** — Language matrix updated: Coda 8 languages, Mist v3 4; expanded API reference.
2. **2026-07-29** — Announced: cloud Arcana switches to Coda on 2026-08-15; migrate `modelId` to `coda`.
3. **2026-07-10** — First-party MCP server launched at `mcp.rime.ai` (voice catalog browsing + synthesis from Claude/OpenAI/IDEs).
4. **2026-06-11** — Speech QA dashboard retired; pronunciation control now API-only with new Phonemize endpoint.
5. **2026-05-19** — Coda released: flagship model, sub-100ms latency, multilingual, word-level timestamps; recommended Arcana successor.
6. **2026-04-24** — On-prem image adds auth env vars `RIME_API_KEY` and `API_KEY_HEADER`.
7. **2026-04-06** — Mist v3 released (`modelId: mistv3`), TTFB well below 100ms; 8 new Arcana speakers.
8. **2026-02-04** — Regional endpoints launched (us-east-1, us-west); Arcana gains JSON WebSockets with word-level timestamps.
9. **2025-09-30** — BREAKING: voice details API renames — `model_id`→`modelId`, `name`→`speaker`, `region`→`dialect`; language values now human-readable.
10. **2025-04-24** — Arcana model launched (`modelId: arcana`) for expressive, natural synthesis.


---

# Part 2 — API Reference: Every Endpoint

Source: docs.rime.ai/api-reference (fetched 2026-08-10). All authenticated endpoints use `Authorization: Bearer YOUR_API_KEY`.

**Base URLs**

| Purpose | URL |
|---|---|
| TTS over HTTP (all model families) | `https://users.rime.ai/v1/rime-tts` |
| WebSocket, raw protocol | `wss://users-ws.rime.ai/ws` |
| WebSocket JSON — Coda / Mist v3 | `wss://users-ws.rime.ai/ws3` |
| WebSocket JSON — Mist v2 | `wss://users-ws.rime.ai/ws2` |
| Voice data (public, no auth) | `https://users.rime.ai/data/voices/...` |
| Utilities (phonemize, textnorm) | `https://optimize.rime.ai/...` |
| Dictionary coverage (OOV) | `https://users.rime.ai/oov` |

**Deprecated:** three `arcana/*` API reference pages (HTTP, WebSockets, WebSockets JSON) exist but are deprecated — not covered here. Use Coda instead.

---

## Coda (conversational flagship)

### POST /v1/rime-tts (streaming HTTP)

`POST https://users.rime.ai/v1/rime-tts` — auth: `Authorization: Bearer YOUR_API_KEY`. Response: audio bytes streamed in the format chosen by the `Accept` header: `audio/webm;codecs=opus` (recommended), `audio/ogg;codecs=opus`, `audio/mpeg`, `audio/wav`, `audio/L16` (headerless PCM), `audio/PCMU` (G.711 μ-law).

| Param | Type | Req | Default | Notes |
|---|---|---|---|---|
| `speaker` | string | yes | — | Must be a Coda voice from the catalog |
| `text` | string | yes | — | Max 1,000 chars per request |
| `modelId` | string | no | — | Set to `"coda"` |
| `lang` | string | no | `en` | ISO 639-1 or 639-2/3: en, es, fr, pt, de, ja, ar, hi |
| `samplingRate` | number | no | 24000 | Hz |
| `timeScaleFactor` | number | no | 1.0 | Range 0.4–2.5; **>1.0 slows down, <1.0 speeds up** |

```bash
curl -X POST https://users.rime.ai/v1/rime-tts \
  -H 'Accept: audio/webm;codecs=opus' \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  --output output.webm \
  -d '{"text":"Hello from Rime!","modelId":"coda","speaker":"astra","lang":"en","samplingRate":24000}'
```

### WebSocket (raw) — wss://users-ws.rime.ai/ws

Auth via `Authorization: Bearer YOUR_API_KEY` header on connect. **Must pass `modelId=coda` in the query string** — otherwise the request routes to Mist v3 and Coda speakers fail.

Query params:

| Param | Type | Req | Default | Notes |
|---|---|---|---|---|
| `speaker` | string | yes | — | Coda voice |
| `modelId` | string | no | `mistv3` | Set to `coda` |
| `audioFormat` | string | no | — | `mp3`, `ogg`, `mulaw`, `pcm` |
| `lang` | string | no | `eng` | ISO 639-1 or 639-2/3 |
| `samplingRate` | int | no | 24000 | Cloud: 8000, 16000, 22050, 24000, 44100, 48000, 96000 |
| `segment` | string | no | `bySentence` | `immediate`, `never`, `bySentence` |

Protocol: client sends **bare text strings** (no JSON); server returns **raw audio bytes**. Inline commands sent as text: `<CLEAR>` (clear buffer), `<FLUSH>` (force synthesis of buffer), `<EOS>` (synthesize, send, close connection).

```python
import asyncio, websockets

async def main():
    url = "wss://users-ws.rime.ai/ws?modelId=coda&speaker=astra&audioFormat=mp3"
    async with websockets.connect(url, additional_headers={"Authorization": "Bearer YOUR_API_KEY"}) as ws:
        await ws.send("Hello from Rime! ")
        await ws.send("<EOS>")
        with open("out.mp3", "wb") as f:
            async for msg in ws:
                f.write(msg)

asyncio.run(main())
```

### WebSocket JSON — wss://users-ws.rime.ai/ws3

Same auth; same `modelId=coda` routing requirement (default is `mistv3`). Query params as raw WS, except `audioFormat` options are `mp3`, `mulaw`, `pcm`; `samplingRate` default 24000 (cloud accepts 8000–96000; on-prem any value). Max 1,000 chars per request. Text buffers until sentence punctuation (`.` `?` `!`) or an explicit flush/eos.

Client → server messages:

```json
{"text": "Hello there.", "contextId": "optional-uuid"}
{"operation": "clear"}   // clear buffer
{"operation": "flush"}   // force synthesis of buffer
{"operation": "eos"}     // synthesize remaining buffer, close connection
```

Server → client events (`contextId` echoes the most recent client-provided ID, else `null`):

| Event | Shape |
|---|---|
| chunk | `{"type":"chunk","data":"<base64 audio>","contextId":str\|null}` |
| timestamps | `{"type":"timestamps","word_timestamps":{"words":[],"start":[],"end":[]},"contextId":str\|null}` — seconds from synthesis start; **English/Spanish only** |
| done | `{"type":"done","contextId":str\|null}` |
| error | `{"type":"error","message":str}` — connection stays open after errors |

---

## Mist v3

### POST /v1/rime-tts (streaming HTTP)

`POST https://users.rime.ai/v1/rime-tts` — Bearer auth. Response: streamed audio bytes per `Accept` header (same six formats as Coda: webm-opus recommended, ogg-opus, `audio/mpeg`, `audio/wav`, `audio/L16`, `audio/PCMU`).

| Param | Type | Req | Default | Notes |
|---|---|---|---|---|
| `speaker` | string | yes | — | From voice catalog |
| `text` | string | yes | — | Max 1,000 chars |
| `modelId` | string | no | — | Set to `"mistv3"` |
| `lang` | string | no | `en` | Must match speaker's language |
| `samplingRate` | number | no | 24000 | Hz |
| `timeScaleFactor` | number | no | 1.0 | 0.4–2.5; >1.0 slower, <1.0 faster |
| `pauseBetweenBrackets` | bool | no | false | `<500>` in text = 500 ms pause |
| `inlineSpeedAlpha` | string | no | — | Comma-separated speeds for `[bracketed]` words; <1.0 faster, >1.0 slower |

```python
import requests

r = requests.post(
    "https://users.rime.ai/v1/rime-tts",
    headers={"Accept": "audio/webm;codecs=opus",
             "Authorization": "Bearer YOUR_API_KEY",
             "Content-Type": "application/json"},
    json={"speaker": "cove", "text": "Hello from Rime!",
          "modelId": "mistv3", "samplingRate": 24000},
    stream=True)
r.raise_for_status()
with open("output.webm", "wb") as f:
    for chunk in r.iter_content(4096):
        f.write(chunk)
```

### WebSocket (raw) — wss://users-ws.rime.ai/ws

Bearer auth header on connect. Query params:

| Param | Type | Req | Default | Notes |
|---|---|---|---|---|
| `speaker` | string | yes | — | From catalog |
| `modelId` | string | no | — | Set to `mistv3` |
| `audioFormat` | string | no | — | `pcm`, `mulaw`, `mp3` |
| `lang` | string | no | `eng` | Must match speaker |
| `samplingRate` | int | no | 22050 | Range 4000–44100 |
| `speedAlpha` | float | no | 1.0 | Speech speed |
| `pauseBetweenBrackets` | bool | no | false | |
| `inlineSpeedAlpha` | string | no | — | Comma-separated speeds for bracketed words |
| `segment` | string | no | `bySentence` | `immediate`, `never`, `bySentence` |

Protocol identical to Coda raw WS: bare text in, raw audio bytes out; `<CLEAR>` / `<FLUSH>` / `<EOS>` commands.

### WebSocket JSON — wss://users-ws.rime.ai/ws3

Bearer auth; `modelId=mistv3` (the default for this route). Query params as the raw WS above. Message protocol and event types identical to the Coda `/ws3` section: send `{"text", "contextId?"}` and `{"operation": "clear"|"flush"|"eos"}`; receive `chunk` (base64), `timestamps` (en/es only), `done`, `error`.

```python
import asyncio, base64, json, websockets

async def main():
    url = "wss://users-ws.rime.ai/ws3?modelId=mistv3&speaker=cove&audioFormat=mp3"
    async with websockets.connect(url, additional_headers={"Authorization": "Bearer YOUR_API_KEY"}) as ws:
        await ws.send(json.dumps({"text": "Hello from Rime.", "contextId": "c1"}))
        await ws.send(json.dumps({"operation": "eos"}))
        audio = b""
        async for msg in ws:
            ev = json.loads(msg)
            if ev["type"] == "chunk":
                audio += base64.b64decode(ev["data"])
            elif ev["type"] == "done":
                break
    open("out.mp3", "wb").write(audio)

asyncio.run(main())
```

---

## Mist v2 (legacy, most parameter-rich)

**Mist v2 speed convention is inverted vs. Coda/v3 `timeScaleFactor`:** `speedAlpha` <1.0 = faster, >1.0 = slower.

Shared body parameters for all Mist v2 HTTP variants (streaming, SSE, JSON):

| Param | Type | Req | Default | Notes |
|---|---|---|---|---|
| `speaker` | string | yes | — | From catalog |
| `text` | string | yes | — | Max 1,000 chars |
| `modelId` | string | no | — | Set to `"mistv2"` |
| `lang` | string | no | `eng` | Must match speaker |
| `samplingRate` | int | no | format-dependent (22050 typical) | Range 4000–44100 |
| `speedAlpha` | float | no | 1.0 | <1.0 faster, >1.0 slower |
| `pauseBetweenBrackets` | bool | no | false | `<milliseconds>` syntax |
| `phonemizeBetweenBrackets` | bool | no | false | `{phonemes}` custom pronunciation |
| `inlineSpeedAlpha` | string | no | — | Comma-separated speeds for `[bracketed]` words |
| `noTextNormalization` | bool | no | false | Skip text norm; reduces latency |

### POST /v1/rime-tts (streaming HTTP)

Bearer auth; response streams audio bytes per `Accept` header:

| Accept | Format | Default rate |
|---|---|---|
| `audio/mpeg` | MP3 | 22050 Hz |
| `audio/L16` | headerless 16-bit LE PCM | 16000 Hz |
| `audio/PCMU` | G.711 μ-law | 8000 Hz |

```bash
curl -X POST https://users.rime.ai/v1/rime-tts \
  -H 'Accept: audio/mpeg' -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Content-Type: application/json' --output out.mp3 \
  -d '{"text":"Hello from Rime!","modelId":"mistv2","speaker":"astra","lang":"eng","samplingRate":22050,"speedAlpha":1.0}'
```

### POST /v1/rime-tts (Server-Sent Events)

Same URL/auth/body params, plus optional `audioFormat` (`mp3`, `mulaw`, `pcm`). Headers: `Accept: text/event-stream`, `Content-Type: application/json`. Stream emits three event types:

```
event: chunk       data: {"data": "<base64 audio>"}
event: timestamps  data: {"word_timestamps": {"words": [...], "start": [...], "end": [...]}}
event: done        data: {"done": true}
```

### POST /v1/rime-tts (JSON envelope — mp3 / wav / ogg / mulaw)

One endpoint, four output encodings selected by required `audioFormat`. Headers: `Accept: application/json`, `Content-Type: application/json`, Bearer auth. Response: JSON envelope containing base64-encoded audio. All shared params above apply.

| `audioFormat` | Encoding in envelope | samplingRate constraints |
|---|---|---|
| `"mp3"` | base64 MP3 | 4000–44100, default 22050 |
| `"wav"` | base64 WAV (16-bit PCM) | 4000–44100, default 22050 |
| `"ogg"` | base64 Opus/Ogg | **required**; only 8000, 12000, 16000, 24000 |
| `"mulaw"` | base64 G.711 μ-law | typically 8000 (telephony) |

```bash
curl -X POST https://users.rime.ai/v1/rime-tts \
  -H 'Accept: application/json' -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello from Rime!","modelId":"mistv2","speaker":"astra","lang":"eng","audioFormat":"mulaw"}'
```

### WebSocket (raw) — wss://users-ws.rime.ai/ws

Bearer auth header; `modelId=mistv2` in query. Query params = the shared Mist v2 table above as query-string args, plus `audioFormat` (`mp3`, `mulaw`, `pcm`) and `segment` (`immediate` | `never` | `bySentence`, default `bySentence`). Protocol: bare text in, raw audio bytes out; buffers until punctuation (`.` `,` `?` `!`); commands `<CLEAR>`, `<FLUSH>`, `<EOS>` as elsewhere.

### WebSocket JSON — wss://users-ws.rime.ai/ws2

Note: Mist v2 uses **`/ws2`** (Coda/v3 use `/ws3`). Bearer auth; required query params `speaker` and `modelId=mistv2`; optional params as raw WS above. Timestamps only for `en`/`eng` or `es`/`spa`.

Client → server: `{"text": "...", "contextId": "optional-uuid"}`, `{"operation": "clear"|"flush"|"eos"}`.
Server → client: `{"type":"chunk","data":"<base64>","contextId":...}`, `{"type":"timestamps","word_timestamps":{...},"contextId":...}`, `{"type":"done","done":true,"contextId":...}`, `{"type":"error","message":...}` (connection stays open after errors).

---

## Data endpoints (public — no auth)

### GET voice details

`GET https://users.rime.ai/data/voices/voice_details.json` — no API key. Returns a JSON array of voice objects:

| Field | Meaning |
|---|---|
| `speaker` | Voice name (value used as `speaker` param) |
| `gender`, `age`, `country`, `dialect`, `demographic` | Subjective descriptors ("meant to serve as a general guide") |
| `genre` | Array of suitable content genres |
| `language` / `lang` | Language name / code to pass as `lang` |
| `modelId` | Model the voice belongs to |
| `flagship` | Optional boolean |

```bash
curl https://users.rime.ai/data/voices/voice_details.json
```

### GET all voices (v2)

`GET https://users.rime.ai/data/voices/all-v2.json` — no API key, no params. Returns `{modelId: {iso639-2 lang code: [voice names]}}`, e.g.:

```json
{"coda": {"eng": ["astra", "albion"], "spa": ["aurelio", "celestino"]},
 "mistv3": {"eng": ["alexis", "astra"], "spa": ["diego", "isa"]}}
```

Pass the same `modelId` from this file to the TTS APIs.

---

## Utility endpoints

### POST /oov — dictionary coverage check

`POST https://users.rime.ai/oov` — Bearer auth. Body param: `text` (string, required) — words separated by spaces, commas, or newlines. Response: JSON array of words **not** in Rime's pronunciation dictionary (`[]` = full coverage). Uncovered words still synthesize via model prediction; verify proper nouns before production. Dictionary additions ~1 week via account manager, or use Phonemize for immediate control.

```bash
curl -X POST https://users.rime.ai/oov \
  -H 'Authorization: Bearer YOUR_API_KEY' -H 'Content-Type: application/json' \
  -d '{"text": "Rime kubernetes acetaminophen"}'
```

### POST /phonemize — audio → Rime phonemes

`POST https://optimize.rime.ai/phonemize` — Bearer auth. Body is **raw audio bytes** (not JSON/multipart); `Content-Type` must be `audio/wav` or `audio/mpeg`. No other params. Response:

```json
{"audioId": "<uuid>", "phonemeString": "<Rime phonetic alphabet>", "authed": 1}
```

`phonemeString` may include punctuation tokens — strip before using in `{phonemes}` brackets.

```bash
curl -X POST https://optimize.rime.ai/phonemize \
  -H 'Authorization: Bearer YOUR_API_KEY' -H 'Content-Type: audio/wav' \
  --fail --data-binary @speech.wav
```

### POST /textnorm — text normalization preview

`POST https://optimize.rime.ai/textnorm` — Bearer auth, JSON body.

| Param | Type | Req | Default | Notes |
|---|---|---|---|---|
| `text` | string | yes | — | Numbers, phone numbers, non-standard words expanded to spoken form |
| `lang` | string | no | `en` | e.g. `en`, `es`, `fr`, `de` |

Response: `{"normalized": "<spoken-form text>"}`.

```bash
curl -X POST https://optimize.rime.ai/textnorm \
  -H 'Authorization: Bearer YOUR_API_KEY' -H 'Content-Type: application/json' \
  -d '{"text":"1234 1,2,3,4 1-800-444-4141"}'
# → {"normalized": "one two three four, one , two , three , four, one, eight hundred, four four four, four one four one"}
```

---

## Cross-family gotchas

- **Speed semantics differ:** Coda/Mist v3 HTTP use `timeScaleFactor` (>1.0 = slower, range 0.4–2.5); Mist v2 (and the v3 WS routes) use `speedAlpha` (<1.0 = faster, >1.0 = slower).
- **WS routing:** `/ws` and `/ws3` default `modelId` to `mistv3` — always pass `modelId=coda` for Coda voices; Mist v2 JSON WS lives on `/ws2`, not `/ws3`.
- **Word timestamps** (SSE and JSON WS) are English/Spanish only.
- **1,000-char limit** applies per request/message across all synthesis endpoints.
- Default sampling rates: 24000 (Coda/v3) vs 22050 (Mist v2); Ogg-in-JSON accepts only 8000/12000/16000/24000.


---

# Part 3 — Text Handling, Pronunciation & Speech Control

## 3.1 Text normalization overview

Rime normalizes non-standard written text into spoken form automatically before synthesis: numbers, currency, dates/times, phone numbers, measurements, addresses, URLs, emails, abbreviations, acronyms, symbols. Send raw text for common formats — do NOT pre-expand what Rime already handles.

**Debugging:** use the `/textnorm` endpoint to see the normalized output of an input string before synthesis (isolates normalization bugs from speech-quality issues). Test realistic dates, currencies, phone numbers, and brand names before production.

**Model feature parity:**

| Feature | Coda | Mist |
|---|---|---|
| Native text normalization | Yes | Yes |
| `spell()` function | Yes | Yes (v3) |
| `phonemizeBetweenBrackets` (custom pronunciation) | No | v1, v2 only (not v3) |
| Custom pause tags `<ms>` | No | Yes (v1, v2, v3) |
| Homograph `word_wordid` tags | No | v2 only |

## 3.2 Handled automatically vs needs pre-expansion

**Handled natively (send as-is):** currency with symbols (`$124.50`), full dates with year (`04/21/2026`), clock times with minutes (`7:05 PM`), phone numbers (US + international, various separators), percentages, standard measurements (`5kg`, `98°F`), URLs/emails, common abbreviations.

**Known gaps — pre-expand these before sending:**

| Pattern | Input | Pre-expand to (spoken form) |
|---|---|---|
| Date without year | `04/21` | `April 21st` |
| Month + year only | `07/2025` | `July 2025` |
| Bare hour, no minutes | `3pm` | `3:00pm` |
| Decades | `1990s` | `the nineteen nineties` |
| Financial periods | `Q1 2025`, `1H 2024` | `first quarter twenty twenty five` |
| Non-dollar scale shorthand | `€900K` | `900 thousand euros` |
| Country + symbol prefix | `AUD$900K` | spell out |
| Very long comma numbers | `10,000,000` | `10M` |
| Negative currency amounts | `-$50` | spell out |
| European 24h with "h" | `15h30` | spell out |
| Approximate times | `9:00-ish` | spell out |
| Superscript exponents, large ordinals | — | spell out |
| Isolated Roman numerals | `XIV` alone | spell out (works after "Chapter"/"Act") |
| Meter/million ambiguity, uncommon units | `5M` | disambiguate |
| Vanity phone letters | `1-800-FLOWERS` | use `spell()` |

Rime's official guidance: pre-normalize ONLY for documented gaps above, or for regeneration consistency in regulated content (legal read-backs). Otherwise verify via `/textnorm` and report gaps to Rime support rather than building your own preprocessor.

## 3.3 Numbers, currency, measurements

| Category | Input | Spoken output |
|---|---|---|
| Cardinal | `123` | one hundred and twenty-three |
| Scientific notation | `1e6` | one million |
| Approximator | `~300` | approximately three hundred |
| Currency | `$1,045.96` | (full spoken currency) |
| Currency shorthand | `$5M` | five million dollars |
| Range (shared unit) | `35-58 mph` | thirty-five to fifty-eight miles per hour |
| Percent | `100%` / `12.5%` / `78-84%` | one hundred percent / twelve point five percent / seventy-eight to eighty-four percent |
| Roman numeral in context | `Chapter IV` | chapter four |

Recognized currency symbols: `$ € £ ¥`; scale abbreviations: `K M B bn`. Decimals, ordinals, fractions, and years all expand. Measurements cover length, mass, volume, temperature, speed, power, percent.

**Standalone symbols:** `&` → "and", `$` → "dollar", `%` → "percent", `#` → "hash".

## 3.4 Dates and times

| Format | Input | Spoken output |
|---|---|---|
| MM/DD/YYYY | `10/12/2024` | october twelfth, twenty twenty-four |
| ISO YYYY-MM-DD | `2021-03-15` | the fifteenth of march twenty twenty-one |
| Dotted M.D.YYYY | `8.8.2018` | august eighth twenty eighteen |
| Month D, YYYY | `April 2, 2024` | april second, twenty twenty-four |
| D Month YYYY | `5 July 2015` | the fifth of july twenty fifteen |
| Year only | `1998` | nineteen ninety-eight |
| Month + year | `May 2019` | may twenty nineteen |
| Month + ordinal | `January 1st` | january first |

US vs ISO formats produce slightly different phrasing — pick one format for consistency.

| Time format | Input | Spoken output |
|---|---|---|
| 12h + meridiem | `3:45pm`, `10:30 AM` | three forty-five PM |
| 24-hour | `15:45` | fifteen forty-five |
| On the hour | `6:00` | six o'clock |
| Dotted meridiem | `6 a.m.` | six AM |
| With timezone | `9:00 AM PST` | nine AM PST |
| Word forms | `noon`, `midnight`, `quarter past 6`, `half past 6` | as written |
| Range | `9:20-9:45` | nine twenty to nine forty-five |

`am/pm` and `a.m./p.m.` both accepted, flexible spacing.

## 3.5 Addresses, URLs, emails

- State abbreviations work in context, but full state names give more consistent results. `Rd.` → "road", `St.` → "saint" or "street" by context.
- URLs: schemes, `www`, and paths are read; common TLDs (`.com .org .io .ai`) spelled letter-by-letter. Internationalized (non-ASCII) domains not supported.
- Emails: a custom segmentation model splits compound words and handles punctuation/TLDs. For unusual emails or vanity URLs, force it with `spell()`.

## 3.6 Abbreviations, acronyms, initialisms

- Titles: `Dr. Smith` → "doctor smith". Latin: `e.g.` → "for example". Streets: `rd.` → "road". `St. John` → "saint john".
- Capital-letter sequences default to acronym (word) pronunciation: `NASA` → "Nasa". Common initialisms (DNA, FBI, CIA) are known and spelled letter-by-letter.
- **Force initialism:** lowercase with periods and spaces — `d. n. a.` → "D N A" (works for `u. p. s.`, `g. p. a.`). Or use `spell()`.

## 3.7 spell() — letter-by-letter reading

Syntax: `spell(content)` — works on any number, letter, or alphanumeric string. Supported on Coda and Mist v3. No parameters.

Grouping logic: groups characters in threes where possible, pairs when necessary, and inserts pauses at letter↔number transitions.

| Input | Spoken output |
|---|---|
| `spell(jonathan)` | J O N, A T H, A N |
| `spell(4252528929)` | 4 2 5, 2 5 2, 8 9, 2 9 |
| `spell(rf543dc2)` | r f, 5 4 3, d c, 2 |
| `spell(help@rime.ai)` | h e l p, at, r i m e, dot, a i |

Symbols inside `spell()`: `@` → "at", `-` → "dash", `_` → "underscore", `.` → "dot".

Use for: confirmation codes, account numbers, SKUs, vanity phone letters (`1-800-spell(FLOWERS)`), unusual emails. Do NOT use for standard phone numbers (native digit grouping is more natural) or real words that happen to be uppercase. Avoid dashes in numeric IDs — use spaces or `spell()`.

## 3.8 Speed control — speedAlpha

`speedAlpha` scales speaking rate. **Direction differs by model:**

| Model | Parameter | Direction |
|---|---|---|
| Mist v2 | `speedAlpha` (native) | < 1.0 = faster, > 1.0 = slower |
| Coda, Mist v3 | `speedAlpha` (back-compat) | inverted: > 1.0 = faster, < 1.0 = slower |
| Coda, Mist v3 | `timeScaleFactor` (preferred) | inverted direction from speedAlpha |

No hard min/max documented; default behavior is 1.0 = normal. Best practice: start near 1.0 and evaluate representative audio before pushing further.

```json
{ "modelId": "mistv2", "text": "Hello, world!", "speedAlpha": 0.85 }
```

Per-word speed: `inlineSpeedAlpha` (Mist v2/v3 only) applies bracketed-text, comma-separated per-word speed values.

## 3.9 Custom pauses

Syntax: angle brackets containing a millisecond value — `<750>` = 750 ms pause.

```
wait. <750> are you actually serious.
```

- Requires request parameter `"pauseBetweenBrackets": true` — silently inert without it.
- Supported: Mist, Mist v2, Mist v3. NOT Coda.
- Custom pauses override Rime's default punctuation-based pause insertion.
- No documented min/max duration limits.

## 3.10 Custom pronunciation (inline phonemes)

Syntax: curly brackets containing a Rime-phonetic-alphabet string — e.g. `{k1Ast0xm}` for "custom".

```json
{
  "text": "actually, {g1orby0ul2Ets} is a word i just made up.",
  "modelId": "mistv2",
  "speaker": "peak",
  "phonemizeBetweenBrackets": true
}
```

- Requires `"phonemizeBetweenBrackets": true`.
- Supported on **Mist v1 and Mist v2 only** — not Mist v3, not Coda. On v3/Coda, use respelling or request a dictionary addition.
- Digits inside the string are stress markers (see 3.12), not characters.

**Workflow (three pronunciation-control methods):**
1. **Coverage API** — check whether a word is already in Rime's dictionary; verify uncommon terms/brand names before production.
2. **Inline custom pronunciation** — as above. Generate phoneme strings with the Phonemize API: `POST https://optimize.rime.ai/phonemize` with `Authorization: Bearer $RIME_API_KEY`, `Content-Type: audio/wav`, WAV body; response includes `"phonemeString": "h0El1o !"` — strip trailing punctuation and wrap: `{h0El1o}`.
3. **Dictionary addition** — email sales@rime.ai / account manager; Rime linguists typically add new words within ~1 week.

## 3.11 Homograph disambiguation (Mist v2 only)

Syntax: append underscore + wordID to the word — `word_wordid`.

```
The produce_nou section is fresh.   vs.   Farmers produce_vrb crops.
```

Rime predicts pronunciation from syntactic context and frequency; the tag overrides the prediction when wrong.

**wordID suffixes:** `nou` noun, `vrb` verb, `adj` adjective, `adj-nou` adjective/noun, `geo` geographic, `corp` corporate, `psy` psychology sense, `nam` brand name, `art` art sense, `jp` Japanese origin; compound IDs like `nou-knot`/`nou-ship` distinguish senses.

| Word | wordID | Example context |
|---|---|---|
| produce | `produce_nou` | The produce section of the store |
| produce | `produce_vrb` | Farmers work hard to produce crops |
| read | `read_past` | He read the letter |
| read | `read_present` | She likes to read novels |
| lead | `lead_nou` | The statue was cast in lead |
| lead | `lead` | He was chosen to lead the team |
| wind | `wind_nou` | The wind rustled the trees |
| wind | `wind_vrb` | Let me wind up this clock |
| tear | `tear_nou` | A tear rolled down her cheek |
| tear | `tear_vrb` | Tear down the wall |
| bow | `bow_nou-knot` | He made a bow with a ribbon |
| bow | `bow_nou-ship` | I walked to the bow of the ship |
| subject | `subject_adj-nou` | the subject of psychology |
| subject | `subject_vrb` | I was subject to experiments |
| refuse | `refuse_nou` | The refuse trailed behind them |
| refuse | `refuse_vrb` | He would refuse to eat vegetables |
| live | `live_adj` | We are broadcasting live |
| live | `live_vrb` | They live in the countryside |

(The docs page carries a much longer full table; pattern is identical.)

## 3.12 Rime phonetic alphabet (complete)

Used inside `{...}` custom-pronunciation brackets. Case-sensitive.

**Vowels**

| Symbol | Example | | Symbol | Example |
|---|---|---|---|---|
| `@` | b**a**t | | `e` | b**ai**t |
| `a` | h**o**t | | `I` | b**i**t |
| `A` | b**u**tt | | `i` | b**ea**t |
| `W` | ab**ou**t | | `o` | b**oa**t |
| `x` | comm**a** | | `O` | b**oy** |
| `Y` | b**i**te | | `U` | b**oo**k |
| `E` | b**e**t | | `u` | b**oo**t |
| `R` | b**ir**d | | `N` | butt**on** |

**Consonants**

| Symbol | Example | | Symbol | Example |
|---|---|---|---|---|
| `b` | **b**uy | | `p` | **p**ie |
| `C` | **Ch**ina | | `r` | **r**ye |
| `d` | **d**ie | | `s` | **s**igh |
| `D` | **th**y | | `S` | **sh**y |
| `f` | **f**ight | | `t` | **t**ie |
| `g` | **g**uy | | `T` | **th**igh |
| `h` | **h**igh | | `v` | **v**ie |
| `J` | **j**ive | | `w` | **w**ise |
| `k` | **k**ite | | `y` | **y**acht |
| `l` | **l**ie | | `z` | **z**oo |
| `m` | **m**y | | `Z` | plea**s**ure |
| `n` | **n**igh | | `G` | si**ng** |

**Stress markers** — digits placed immediately before the vowel:
- `1` primary stress: `{k1am0x}` = "comma"
- `2` secondary stress: `{2akS0In1ir}` = "auctioneer"
- `0` unstressed: mark every remaining vowel with `0`

## 3.13 Prompting guidance (voice agents)

Core rule: write for speech, not text. Put concrete example patterns in the system prompt — abstract instructions like "be conversational" don't work.

**Dos**
- Give the LLM good/bad example pairs to pattern-match:

| Bad (written prose) | Good (spoken) |
|---|---|
| "I can certainly assist you with that inquiry." | "Yeah, I can help with that. One sec." |
| "Unfortunately, I am required to inform you..." | "So... I'm not going to be able to do that today." |
| "I will now transfer you..." | "Okay, one moment. I'm going to grab someone..." |

- Sprinkle disfluencies ("um", "uh", "yeah", "well", "so", "I mean", "you know") — but don't stack: two "um"s in a row reads as a bug.
- Use punctuation as prosody (Coda has no SSML): comma = short pause + slight rise; period = falling pitch; `?` = rising intonation; `...` = hesitant/trailing pause (sparingly); semicolon = between comma and period.
- Keep sentences under 25 words; long sentences without internal commas sound breathless.
- Express personality via observable behavior ("starts sentences with 'yeah'"), not adjectives ("friendly").
- Keep a calm baseline; save `!` for moments that warrant it.
- Pre-expand the gap patterns from §3.2; wrap IDs/codes in `spell()`.

**Don'ts**
- Don't pre-normalize what Rime handles natively (currency, full dates, times with minutes, phone numbers, percentages, measurements).
- Don't use `spell()` on standard phone numbers or on real uppercase words.
- Don't use dashes inside numeric IDs (use spaces or `spell()`).
- Never invent, drop, or reorder information while rewriting for speech — preserve every digit, letter, and symbol; change only surface form.

## 3.14 Linguistics background

TTS is a one-to-many problem: one text string maps to infinite acoustic realizations. Rime picks an opinionated, fluent default out of the box, then exposes low-level overrides (custom pauses, custom pronunciations, homograph tags, speed) for the cases where the default is wrong.


---

# Part 4 — Voice Agents & Platform Integrations

## 4.1 Voice Agent Architecture (shared across all framework tutorials)

Rime positions itself as the **speech layer only**. A voice agent has four layers:

1. **Audio transport** — carries mic input and synthesized audio
2. **Speech recognition (STT)** — user audio → text
3. **Agent logic (LLM)** — decides the response
4. **Speech generation (TTS)** — Rime turns text into audio

Loop: **mic → STT → agent logic/LLM → Rime TTS → playback**.

**API key rule (all tutorials): keep `RIME_API_KEY` on the server.** The browser never calls Rime directly — it calls an app-server proxy route (or a server-side WebSocket bridge) which forwards to Rime with `Authorization: Bearer $RIME_API_KEY`.

Orchestration options Rime documents:
- **Complete framework**: LiveKit voice agent (browser-based, end-to-end)
- **Direct-API starters**: Next.js, Vite + React, Express, Node.js, FastAPI
- **Supported platforms**: LiveKit, Pipecat, Vapi, Daily
- **Low-level**: WebSocket API for custom synthesis

### Common pattern in all five framework starters

- **STT**: browser-native `SpeechRecognition` API (Chrome/Edge/Safari)
- **LLM**: stub `respond()` function — "replace this with a call to your LLM of choice"
- **TTS**: Rime **Coda** model, `POST https://users.rime.ai/v1/rime-tts`
- **Body params**: `{ text, speaker, modelId }` (defaults: `speaker: "astra"`, `modelId: "coda"`), header `Accept: audio/mpeg`
- Server proxy route at `/api/tts`; client posts text, gets audio bytes back, plays them.

Canonical proxy call (JS variants all use this):

```javascript
const rimeRes = await fetch("https://users.rime.ai/v1/rime-tts", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.RIME_API_KEY}`,
    "Content-Type": "application/json",
    Accept: "audio/mpeg",
  },
  body: JSON.stringify({ text, speaker, modelId }),
});
```

## 4.2 Per-framework differences

### Node.js (no framework)
- Zero npm deps: `node:http` + `fetch` only. `server.mjs` + `index.html`.
- Flow: browser (mic + playback) → `POST /api/tts` (node:http) → Rime.
- Run: `export RIME_API_KEY=...`, `node server.mjs`, open `http://localhost:3000`.

### Express
- Same loop; Express is the only dependency (Node 20.11+). Route returns audio via
  `res.send(Buffer.from(await rimeRes.arrayBuffer()))`.

### FastAPI (Python)
- Deps: `fastapi uvicorn httpx`. Proxy endpoint uses async `httpx`:

```python
@app.post("/api/tts")
async def tts(req: TTSRequest) -> Response:
    async with httpx.AsyncClient(timeout=30.0) as client:
        rime_res = await client.post(
            RIME_TTS_URL,
            headers={"Authorization": f"Bearer {RIME_API_KEY}", "Accept": "audio/mpeg"},
            json=req.model_dump(),
        )
```
- Tutorial suggests testing the proxy with curl before wiring the UI.

### Next.js
- Key in `.env.local`; proxy is an App Router route at `app/api/tts/route.ts` (same fetch as above, TypeScript). Optional WebSocket upgrade for lower-latency streaming.

### Vite + React
- Vite alone is frontend-only, so a small Express `server.mjs` proxies synthesis; Vite dev server proxies `/api` to it. Key stays in the Node process env.

## 4.3 Platform integrations

### LiveKit (quickstart-livekit.md, livekit.md)
- LiveKit owns real-time transport/orchestration; Rime streams the agent's speech via LiveKit's Rime plugin (HTTP synthesis wrapped for streaming with LLM output).
- Setup: Python 3.10+, `.env` with `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `OPENAI_API_KEY`, `RIME_API_KEY`; dep `"livekit-agents[openai,rime,silero,turn-detector]~=1.6"`; `uv sync`, then `uv run agent.py dev`.
- Pairing: STT `openai.STT(model="gpt-4o-transcribe")`, LLM `openai.LLM(model="gpt-4o-mini")`, VAD Silero, turn detector plugin.

```python
from livekit.plugins import rime
tts = rime.TTS(model="coda", speaker="lyra")
```
- Rime params: `model="coda"`, `speaker` (e.g. `lyra`, `astra`; see Voices page). Full plugin reference: docs.livekit.io/agents/integrations/rime/.

### Pipecat
- Class: **`RimeTTSService`** (`RimeNonJsonTTSService` is deprecated).
- Setup: Python 3.11+, `.env` with `RIME_API_KEY` + `OPENAI_API_KEY`, dep `pipecat-ai[openai,rime,silero,webrtc,runner]>=1.5.0,<2`, `uv sync`, `uv run agent.py`, client at `http://localhost:7860/client`.
- Pairing: `OpenAISTTService` (`gpt-4o-transcribe`) + `OpenAILLMService` (`gpt-4o-mini`), Silero VAD.

```python
tts = RimeTTSService(
    api_key=os.getenv("RIME_API_KEY"),
    settings=RimeTTSService.Settings(voice="lyra", model="coda"),
)
```
- Rime params: `voice` (`lyra`, `astra`, ...), `model` (`coda`, `mistv3`, `mistv2`), `api_key`.

### Daily
- Overview page only: Daily is the transport; Rime plugs in through the Pipecat pipeline (see Pipecat guide above; transport docs at docs.pipecat.ai/server/services/transport/daily). No Daily-specific class or params documented on Rime's page.

### Vapi
- Dashboard-based, no code. Assistant → **Voice** tab → provider **"Rime AI"** → pick voice (e.g. celeste, orion, andromeda) → model **Coda** (Arcana deprecated as of 2026-08-15) → publish.
- BYO key (optional, otherwise Vapi's integrated billing): Build → More → Integrations → Rime → add key from app.rime.ai/tokens.

### SignalWire
- Overview page: Rime voices are available in SignalWire's platform for phone/real-time apps; setup lives in SignalWire's developer docs (developer.signalwire.com). Live demo: MovieBot at 320-4MOVIES, using the `spore` voice on **Mist v2**. No snippet on Rime's page.

### VideoSDK
- Uses VideoSDK's **"RimeAI TTS plugin"**; config documented at docs.videosdk.live/ai_agents/plugins/tts/rime-ai-tts. Demo repo: github.com/videosdk-community/videosdk-rimeai-tts-demo. No snippet/params on Rime's page.

### Together AI
- Rime models hosted on Together's inference platform: **Arcana v3, Arcana v2, Mist v2**. Endpoint/auth/deployment via Together's docs (docs.together.ai). No snippet on Rime's page.

### Baseten (self-hosted engine)
- Single-container deployment: engine validates its own license and serves TTS directly (no separate router). Requires contacting help@rime.ai for engine image + license.
- Baseten workspace secrets: `gcp_rime_service_account`, `rime_license`, `rime_api_key`.
- Steps: clone `rimelabs/rime-baseten-deploy` → pick model dir (Coda v1 = flagship expressive, Mist v3 = low-latency conversational) → set secrets → `truss push .` → autoscaling target ~10 concurrent requests/replica.
- Callers authenticate to Baseten only (Rime key baked into deployment):

```python
resp = requests.post(
    "https://model-<model-id>.api.baseten.co/environments/production/sync",
    headers={"Authorization": f"Api-Key {BASETEN_API_KEY}",
             "Accept": "audio/webm;codecs=opus"},
    json={"text": "...", "speaker": "luna", "lang": "en"},
)
```

### Cerebrium (serverless deployment)
- Rime runs on Cerebrium serverless GPU infra with REST + WebSocket interfaces and autoscaling.
- Steps: Cerebrium secret `RIME_API_KEY` → `cerebrium init rime` (CLI v1.39.0+) → edit `cerebrium.toml` `[cerebrium.runtime.rime]` (GPU/memory/CPU, scaling, region) → `cerebrium deploy`.
- REST: `https://api.cortex.cerebrium.ai/v4/<project-id>/rime` with Rime key in Authorization header; params: text, speaker, model.

### Replit
- Agent-built voiceover-studio app; key stored in Replit **Secrets** (`Cmd/Ctrl+K` → Secrets → `RIME_API_KEY`) so it "never reaches browser code"; backend proxies to `POST https://users.rime.ai/v1/rime-tts` with `modelId: "coda"`.
- Coda voices listed: luna, astra, sirius, estelle, lyra, vespera, masonry, eliphas, arcade, atrium, eucalyptus, fern, stucco, transom, oculus, moss.

### Lovable
- Prompt Lovable with the Rime endpoint/auth details; it generates an **Edge Function** that calls Rime, with the key in **Lovable Cloud → Secrets** (never in frontend code).
- Body: `modelId: "coda"`, `lang: "eng"`, `speaker` from Coda voices (luna, astra, sirius, estelle, lyra, vespera, orion, eliphas, arcade, atrium, eucalyptus, fern, stucco, transom, oculus, moss). Example app: rime.lovable.app.

### OpenClaw
- OpenClaw = assistant workflow platform (skills/plugins); tutorial builds a Telegram bot where the **`rime-reader` skill** replaces OpenClaw's built-in TTS. Three delivery modes: verbatim reading, summarized narration, two-voice podcast discussion.
- Steps: BotFather token + `RIME_API_KEY` in `~/.openclaw/.env` → enable Telegram plugin in `~/.openclaw/openclaw.json` → disable built-in auto-TTS and deny default TTS tool → `git clone https://github.com/rimelabs/rime-reader-openclaw ~/.openclaw/skills/rime-reader` → enable skill, update `SOUL.md`.

```python
def synthesize(text, voice, speed, lang, api_key, model="coda"):
    body = {
        "text": text,
        "speaker": voice,
        "modelId": model,
        "samplingRate": SAMPLE_RATE,   # 48000
        "speedAlpha": speed,
    }
```
- Rime params: `speaker` (atrium, lyra, transom, parapet, fern, thalassa, truss, sirius, eliphas, lintel), `modelId: "coda"`, `samplingRate: 48000`, `speedAlpha` (tempo), Bearer auth.

## 4.4 STT/LLM pairings at a glance

| Tutorial | STT | LLM | TTS model |
|---|---|---|---|
| Node/Express/FastAPI/Next.js/Vite starters | browser `SpeechRecognition` | stub (BYO LLM) | Coda (`astra` default) |
| LiveKit quickstart | OpenAI `gpt-4o-transcribe` | OpenAI `gpt-4o-mini` | Coda (`lyra`) |
| Pipecat | OpenAI `gpt-4o-transcribe` | OpenAI `gpt-4o-mini` | Coda (`lyra`) |
| Vapi / SignalWire / VideoSDK | platform-managed | platform-managed | Coda (Vapi), Mist v2 (SignalWire demo) |


---

# Part 5 — CLI, MCP Server, On-Prem & Platform Admin

## 5.1 Rime CLI

Synthesizes AI speech from the terminal: streams audio during generation, plays it live with a waveform visualization, supports multiple output formats.

### Install

```bash
curl -fsSL https://rime.ai/install-cli.sh | sh        # direct
brew tap rimelabs/rime-cli && brew install rime-cli    # Homebrew
rime --version                                         # verify
```

If `command not found: rime` after script install: open a new terminal or `source ~/.zshrc` / `~/.bashrc`.

### Global flags & environment variables

| Global flag | Purpose |
|---|---|
| `--quiet` / `-q` | Suppress non-essential output |
| `--json` | JSON output |
| `--env` / `-e` | Select a named environment from config |
| `--config` / `-c` | Custom config file path |
| `--version` / `-v` | Version info |
| `--help` / `-h` | Help |

| Env var | Purpose | Default |
|---|---|---|
| `RIME_CLI_API_KEY` | API key (overrides config file) | — |
| `RIME_API_URL` | API endpoint (overrides config file) | — |
| `RIME_AUTH_HEADER_PREFIX` | Authorization header format | `Bearer` |
| `RIME_DASHBOARD_URL` | Dashboard used by `rime login` | `https://app.rime.ai` |

Resolution: env vars > config file (`~/.rime/rime.toml`, TOML with `default_env` plus `[env.name]` sections each holding `api_url`, `api_key`, `auth_header_prefix`) > defaults. Named environments override top-level settings.

Audio format defaults: **WAV** for coda/arcana/arcanav2/mistv3; **MP3** for mistv2/mist (`mist`/`mistv2` only support MP3 — use `-f mp3`). Files embed metadata (voice, model, text) via WAV LIST/INFO chunks or MP3 ID3v2.3 tags.

### Subcommands

**`rime login`** — Browser OAuth against the Rime dashboard; a local callback server receives the API key, validates it, and saves it to `~/.rime/rime.toml`. No flags.
```bash
rime login
```

**`rime logout`** — Removes the saved key by deleting `~/.rime/rime.toml`. No flags.
```bash
rime logout
```

**`rime key`** — Prints the resolved API key (no trailing newline); resolves from config or `RIME_CLI_API_KEY` using the active environment. Used as `$(rime key)` in generated curl commands.
```bash
export KEY=$(rime key)
```

**`rime tts TEXT`** — Synthesize and play or save.
Flags: `--speaker/-s` (voice, required), `--model-id/-m` (`coda`|`mistv3`|`mistv2`|`mist`, required), `--output/-o` (file; `-` = stdout), `--play/-p` (default when no output), `--lang/-l` (default `eng`), `--format/-f` (wav|mp3), `--speed-alpha` (speed multiplier), `--sampling-rate` (Hz), `--inline-time-scale-factor`, `--pause-between-brackets` (all modern models), `--phonemize-between-brackets`, `--no-text-normalization` (mist/mistv2 only). Languages: coda = eng/spa/fra/por/ger/jpn; mist family = eng/fra/ger/spa.
```bash
rime tts "Hey, how's it going?" -s celeste -m coda -o welcome.wav
```

**`rime curl [TEXT]`** — Emits a ready-to-run curl request (run bare for an example; with text, `--speaker` and `--model-id` are required).
Flags: `--speaker/-s` (default `astra`), `--model-id/-m` (default `coda`), `--lang/-l` (default `eng`), `--speed-alpha` (default `1`, must be > 0), `--sampling-rate`, `--oneline` (single-line output), `--api-url`, `--inline-time-scale-factor`, `--pause-between-brackets`, `--phonemize-between-brackets`, `--no-text-normalization`, `--max-tokens` (Arcana, default `1200`, range 200–5000).
```bash
rime curl "Hello from Rime" -s astra -m coda --oneline
```

**`rime hello`** — Time-appropriate greeting (Astra voice, Coda model); smoke test.
Flags: `--output/-o`, `--api-url`; global `--json` works.
```bash
rime hello -o greeting.wav
```

**`rime play FILE`** — Play a WAV file with terminal waveform visualization.
```bash
rime play welcome.wav
```

**`rime config`** — Manage `~/.rime/rime.toml`.
- `init` (`--force`): create config with interactive key prompts; pre-configures `users` (`https://users.rime.ai/v1/rime-tts`) and `users-east` environments.
- `list` (`--json`): show environments, active default starred.
- `default [NAME]`: get or set active environment.
- `show` (`--env/-e`, `--json`, `--show-key`): resolved config incl. key source.
- `add NAME` (`--url` default `https://users.rime.ai/v1/rime-tts`, `--key`, `--auth-prefix`): add environment.
- `rm NAME` (`--yes/-y`): remove environment.
- `edit`: open config in `$VISUAL`/`$EDITOR`/nano/vi.
```bash
rime config default users-east
```

**`rime speedtest`** — Measures TTFB by sending TTS requests to endpoints; tests all configured environments by default.
Flags: `--model/-m` (default `coda`), `--runs` (default `1`), `--timeout` (default `10s`), `--url` (repeatable; alone, tests only given URLs), `--env` (repeatable), `--yes/-y` (auto-switch to fastest environment).
```bash
rime speedtest --runs 3 -y
```

**`rime usage`** — Daily character consumption over the past week, split by Mist/Arcana/Coda.
Flags: `--csv` (default false); `--json` supported.
```bash
rime usage --csv
```

**`rime uninstall`** — Removes binary, config, and PATH entries; detects install method (Homebrew installs print `brew uninstall rime` instead of executing).
Flags: `--yes/-y`.
```bash
rime uninstall -y
```

### Troubleshooting quick hits
- "API key not found" → `rime login` or `export RIME_CLI_API_KEY=...`; "invalid API key" → verify at app.rime.ai/tokens.
- No playback in headless/Docker environments → must use `-o FILE`.
- mist/mistv2 format errors → add `-f mp3`.

## 5.2 MCP Server

**URL:** `https://mcp.rime.ai` (also `/mcp` endpoint). **Transport:** Stateless Streamable HTTP. Aimed at exploration/prototyping; use streaming APIs or generated Pipecat/LiveKit code for production.

### Connecting

| Client | How |
|---|---|
| Claude Code | `claude mcp add --transport http rime https://mcp.rime.ai --header "Authorization: Bearer $RIME_API_KEY"` (omit `--header` for keyless use) |
| Claude.ai / Claude Desktop | Settings → Connectors → Add custom connector → `https://mcp.rime.ai` |
| OpenAI Codex (CLI) | `codex mcp add rime --url https://mcp.rime.ai --bearer-token-env-var RIME_API_KEY` |
| OpenAI Codex (config) | `~/.codex/config.toml`: `[mcp_servers.rime]` with `url = "https://mcp.rime.ai"`, `bearer_token_env_var = "RIME_API_KEY"` |
| Cursor / Windsurf / other JSON clients | `{"mcpServers": {"rime": {"url": "https://mcp.rime.ai", "headers": {"Authorization": "Bearer YOUR_RIME_API_KEY"}}}}` |

Verify connectivity with a `list_voices` call (needs no key).

### Authentication

Keys come from https://app.rime.ai/tokens (same keys as the REST API). Header resolution order:
1. `Authorization: Bearer <key>` (recommended)
2. `X-Rime-Api-Key: <key>` (for clients that restrict the Authorization header)

Server is stateless — never stores credentials; extracts the key per request and forwards it to the Rime API. No key: `list_voices`, `get_voice_details`, `generate_integration`. Key required: `check_dictionary`, `normalize_text`, `synthesize_speech`. Calling a gated tool without a key returns a sign-up pointer, not an error. `synthesize_speech` consumes credits like any API request.

### Tools

| Tool | Key? | Inputs | Output |
|---|---|---|---|
| `list_voices` | No | `model` (opt, e.g. `coda`), `language` (opt, ISO 639-2 e.g. `spa`), `limit` (opt, per model+language cap) | JSON `{ modelId: { langCode: [speaker, ...] } }` with truncation notes |
| `get_voice_details` | No | `speaker`, `model`, `gender`, `language` (all optional filters) | Voice metadata: gender, age, accent, country, genre, model, `lang` value for synthesis |
| `synthesize_speech` | Yes | `text` (max 2,000 chars), `speaker` (default `lyra`), `modelId` (`coda`\|`mistv3`, default `coda`), `language` (opt, auto-inferred), `include_audio` (bool, default false) | MP3 sample via inline player / play URL / audio block |
| `normalize_text` | Yes | `text` (required) | The exact string the TTS model will speak (dates, numbers, phone, currency, abbreviations) |
| `check_dictionary` | Yes | `text` (required; words separated by spaces/commas/newlines) | List of out-of-dictionary words (empty = full coverage); OOD words still synthesize |
| `generate_integration` | No | `framework` (`pipecat`\|`livekit`, required), `language` (`python`\|`node`, default `python`, LiveKit only), `model` (default `coda`), `speaker` (default `lyra`), `mode` (`plugin`\|`inference`, default `plugin`, LiveKit only) | Ready-to-run agent code + install commands + env notes; runs server-side, no credits |

One-liners: `list_voices` browses the catalog by model/language; `get_voice_details` gives demographics for picking a voice; `synthesize_speech` generates an MP3 audition sample; `normalize_text` previews exactly what will be spoken; `check_dictionary` flags words needing custom pronunciations; `generate_integration` scaffolds a Pipecat or LiveKit voice agent.

### Audio delivery (`synthesize_speech`)
1. **Inline player** (MCP Apps hosts like Claude) — MP3 travels outside model context, zero tokens; default.
2. **Play URL** — short-lived link at `structuredContent.audioUrl`; e.g. `curl -s <audioUrl> -o /tmp/rime.mp3 && (afplay ... || ffplay -nodisp -autoexit ... || mpv ...)`. Expired links require re-synthesis.
3. **MCP audio block** — `include_audio: true` returns base64 MP3 in context (costs tokens; prefer 1 or 2).
Hosts that render none still get a text summary + structured result.

### Starter prompts (optional shortcuts)
- `find_a_voice` — recommend and sample voices; arg `description` (opt, e.g. "warm female American, conversational").
- `check_script_pronunciation` — runs `check_dictionary` + `normalize_text` over a script; arg `text` (required).
- `build_voice_agent` — starter code via `generate_integration`; args `framework` (opt, `livekit`|`pipecat`), `use_case` (opt).

## 5.3 On-Prem Deployment

### Hardware & software requirements
- GPU: Mist — NVIDIA T4/L4/A10+; Arcana — A100, H100 MIG `3g.40gb`+; Coda — confirm with Rime first.
- 50 GB storage, 8 vCPUs, 32 GiB RAM.
- OS: Debian 12 (bookworm) or Ubuntu Server 24.04 (noble), x86_64.
- NVIDIA driver ≥ 525.60.13 (recommend 570.133.20+), Docker, NVIDIA Container Toolkit. Verify GPU: `docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubi9 nvidia-smi`.

### Deploy steps (condensed)
1. Get registry key + license from Rime (help@rime.ai), then `cat KEY-FILE | docker login -u _json_key --password-stdin https://us-docker.pkg.dev`.
2. Pull images — all published together under one `YYYYMMDD` tag (current: `20260801`); never mix tags:
   - API: `us-docker.pkg.dev/rime-labs/api/service:<tag>`
   - Mist v3: `us-docker.pkg.dev/rime-labs/mist/v3/omni:<tag>`
   - Coda v1: `us-docker.pkg.dev/rime-labs/coda/v1/coda:<tag>`
   - Arcana v2: `us-docker.pkg.dev/rime-labs/arcana/v2/<language>:<tag>`; Arcana v3: `.../arcana/v3/ennea:<tag>`
3. `docker compose up -d`; allow ~5 min model warm-up.
4. Verify: `curl http://localhost:8000/health` → `{"apiStatus":"ok", "licenseStatus":"valid", "modelReachable":true, ...}`; then POST TTS to `http://localhost:8000` with `Authorization: Bearer <API_KEY>` (JSON default; `Accept: audio/mpeg` for MP3, `Accept: audio/L16` for PCM).

Ports: **8000** HTTP, **8002** binary WebSocket, **8003** JSON WebSocket, 8001 deprecated Mist WS (Spanish unsupported on 8003/8001). Outbound HTTPS required to `optimize.rime.ai/usage`, `optimize.rime.ai/license`, and `us-docker.pkg.dev` (license verification).

Key env vars: `RIME_API_KEY` (pre-configured key), `API_KEY_HEADER` (default `Authorization`), `PLATFORM_API_KEY` (inter-container auth), `MODEL_URL` (default `http://model:8080/invocations`), `ARCANA_{ENG,SPA,FRA,GER}_MODEL_URL` (language routing).

### Performance tuning
Watch: TTFF/TTFB (request → first frame), RTF (processing time / stream duration; must stay ≤ 1), concurrency at target latency.

| Knob | Model | Default | Note |
|---|---|---|---|
| `GENERATOR_MAX_BATCH` | Coda, Arcana | 32 | Raise to 64/128 for higher traffic or newer GPUs |
| `DECODER_MAX_BATCH` | Arcana | 32 | |
| `DECODER_NUM_SESSIONS` | Arcana | 6 | |
| `GENERATOR_GPU_MEMORY_UTILIZATION` | Arcana | 0.8 | Lower on OOM |

Method: benchmark with Rime's `armchair` tool; raise batch sizes while RTF ≪ 1, lower GPU memory utilization on OOM, iterate. Reference: Arcana v2 on H100 — ~400 ms avg initial latency, 32 concurrent at 100% success, P99 ≤ 1 s.

### Load balancing
Use the **ORCA cost-header signal**: responses carry an `endpoint-load-metrics` header (`application_utilization`, `cpu_utilization`, `mem_utilization`, `rps_fractional`, `eps`); full set from Arcana containers since release `20260115`. `application_utilization` = concurrent inference requests / `INFERENCE_CONCURRENCY_CAPACITY` (env var, set after tuning). It only informs the balancer — it does not reject or queue overflow.

### Metrics
- **API container** — `/health` on 8000: `apiStatus`, `timestamp`, `licenseStatus`, `modelReachable`.
- **Arcana container** — liveness `/readyz` on 8080; OTel metrics via `OTEL_COLLECTOR_PROTOCOL`/`OTEL_COLLECTOR_ENDPOINT`: `rime.engine.concurrent_pipeline`, `rime.engine.generated_audio_duration` (s), `rime.engine.gpu_load`, `rime.engine.initial_latency` (ms), `rime.engine.invocation_request`; vLLM Prometheus metrics at `:${GENERATOR_VLLM_PORT}/metrics`; histograms tunable via `HISTOGRAM_BUCKETS_*` / `HISTOGRAM_SUFFIX_*`.
- **Mist container** — `/livez` + `/readyz` on 8080; Prometheus at `:${GENERATOR_SERVICE_PORT}/metrics`: `http_requests_total`, `http_errors_total`.

### Prometheus
Set `GENERATOR_SERVICE_PORT` explicitly (e.g. 30000) on the model container, then add a scrape job to `prometheus.yml` (`scrape_interval: 5s`, `job_name: "model-rime-tts"`, `targets: ["<instance_ip>:30000"]`, `metrics_path: "/metrics"`); run `docker run -d --rm -p 9090:9090 -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus:latest`; confirm the target is UP under Status → Targets at `http://localhost:9090`. Grafana can read from Prometheus for dashboards/alerts.

## 5.4 Teams

- Create at dashboard Settings → Team. Irreversible; the creator's Stripe account becomes the billing account for all team API usage. Each user can belong to only one team.
- Invite via the Team page's Invite tab (email + role).
- Roles: **Owner** — invite members, edit billing, view all API keys, create keys, delete any member's keys, remove members. **Member** — create own API keys only.
- Billing aggregates usage from all members' keys to the creator's Stripe account; billing email changes via Usage and Billing → Manage Billing.
- Removing a member transfers their API keys to the removing owner; at least one owner must remain, and the billing-email holder cannot be removed.

## 5.5 Voice Cloning (Enterprise)

- Custom voices trained on Rime's foundational models (Coda, Arcana, Mist, or combinations); each clone gets a unique UUID for API access. Growth and Enterprise plans only.
- Audio: 30–60 min clean, consistent recordings minimum; 2–5+ hours for strongest results. Mono, lossless (`.wav`/`.flac`), ≥ 44.1 kHz, ≥ 16-bit.
- Recording: low-reverb space, single speaker, consistent mic/distance/energy, pop filter, keep natural breaths/pauses, record across multiple days, 3–4 s of silence between script lines. Include brand terms, alphanumerics, and target use-case delivery (outbound/inbound).
- Process: prepare audio → deliver to the Rime team with chosen foundational model(s) → Rime assigns UUID and enables API access. Turnaround: under seven business days, demand-dependent.


---
