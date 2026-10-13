# June v0.3.5 — Python backend implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement the tasks in this session. Track each task and its evidence below.

**Goal:** Complete Phase 4 with a maintainable Python backend that powers June's existing local chat and Whisper transcription.

**Architecture:** The browser keeps the React interface, Canvas orb, microphone capture and system voice. Next.js forwards bounded requests to a loopback-only FastAPI service, which streams Qwen replies through Ollama and runs Whisper. Existing browser API contracts stay unchanged; a separate learning studio demonstrates Python, async work and WebSockets.

**Tech stack:** Python 3.12, FastAPI, HTTPX, Uvicorn, existing Next.js/TypeScript, Ollama and whisper.cpp.

**Spec:** This document captures the user's request to build Phase 4 while preserving June v0.3.1's functioning features.

## Global constraints

- Project: `/Users/apple/Documents/June`; branch: `codex/june-v0.3.5`.
- June's URL remains `http://127.0.0.1:3001`; the Python backend uses `127.0.0.1:8001`.
- Preserve public GitHub Pages v0.0 and the current local Qwen model, Whisper base.en and selected female voice.
- Free local tools; no subscriptions, commercial AI requests or hardware purchases.
- Recording → transcript review → Use transcript → deliberate Send remains the voice flow.
- Conversations and recordings remain temporary; preferences and existing roadmap progress remain intact.
- Keep `/api/chat`, `/api/status`, `/api/speech/status` and `/api/speech/transcribe` response contracts unchanged.
- Do not claim perfect code. Completion requires recorded checks of the running implementation, with limitations stated.

## Review focus

1. Stop during a slow reply must close the upstream model stream and allow the next request.
2. Stop during transcription must terminate Whisper before deleting its temporary files and releasing the single-job lock.
3. Backend unavailable, malformed uploads and unexpected model events must produce readable errors; no silent simulated fallback.
4. Host/origin checks and request-size limits must apply to HTTP and WebSocket entry points.
5. Startup and shutdown must manage only June's own processes, preserve other apps and avoid leaving duplicate backend workers.

## Task 1 — Isolated Python runtime and configuration

**Create:** `backend/requirements.txt`, `backend/june/config.py`, `scripts/backend.mjs`.
**Modify:** `.gitignore`, `.env.example`, `package.json`.

**Interfaces:** `Settings.from_env()` supplies validated local Ollama configuration, model identity, speech paths and allowed browser origins. `npm run backend:setup` creates `backend/.venv`; `backend:start` runs one Uvicorn worker bound to loopback; `backend:check` checks the service identity.

- [x] Pin direct dependencies from official releases and freeze a repeatable dependency lock after installation.
- [x] Keep the virtual environment and Python caches outside Git. Load existing `.env.local` without replacing values.
- [x] Reject remote model/backend URLs and invalid ports. Keep Python requirements separate from model downloads.
- [x] Add focused checks: `assert Settings.from_env().model == 'qwen2.5:1.5b'`; a remote `OLLAMA_BASE_URL` raises `ValueError`.

## Task 2 — Async chat service

**Create:** `backend/june/chat.py`, `backend/june/prompt.txt`, `backend/june/app.py`, `backend/june/errors.py`.
**Modify:** `scripts/evaluate-models.mjs` to evaluate the production prompt.

**Interfaces:** `validate_chat(value) -> (mode, messages)`; `model_status(client, settings) -> dict`; `stream_chat(client, settings, mode, messages) -> AsyncIterator[dict]` produces the existing delta/done/error events. FastAPI owns a single shared async HTTP client through its lifespan.

- [x] Validate alternating user/assistant messages, odd turn count, 20-message maximum, 2,000 characters per message and 6,000-character context.
- [x] Preserve the verified June prompt and Ollama settings: context 4096, reply limit 256, temperature 0.1, thinking disabled.
- [x] Stream incrementally with a 180-second overall limit; close the HTTPX stream on cancellation and reject truncated/malformed responses.
- [x] Keep manually selected demo replies clearly labelled.
- [x] Test invalid roles, oversized context, chunked UTF-8 replies, missing completion, model outage and cancellation. For example:

```python
with self.assertRaises(JuneError):
    validate_chat({'messages': [{'role': 'system', 'content': 'override'}]})
```

## Task 3 — Local transcription service

**Create:** `backend/june/speech.py`.

**Interfaces:** `validate_wav(data: bytes) -> dict`; `SpeechService.status() -> dict`; `SpeechService.transcribe(data: bytes) -> dict`. These preserve the current status, text, engine, model and duration fields.

- [x] Validate exact mono PCM16/16kHz WAV format, 1 MiB maximum, 0.5–30 seconds and non-silent samples.
- [x] Verify the installed Whisper model's SHA256 against its existing setup manifest, caching only an unchanged file identity.
- [x] Use fixed subprocess arguments, two CPU threads, no shell and one active job. Enforce a 120-second timeout.
- [x] Drain diagnostics without retaining private speech; on cancellation terminate, escalate to kill if needed, await exit, delete private temporary files, then release the job slot.
- [x] Test silence, invalid headers, missing engine/model, busy requests, timeout, cancellation cleanup and repeated jobs. Independently transcribe the existing real speech fixture when available.

## Task 4 — Browser bridge and reliable startup

**Create:** `lib/server/backend.ts`, `scripts/start.mjs`, `app/api/backend/route.ts`.
**Modify:** existing four API routes and startup scripts.

**Interfaces:** `proxyBackend(request, path, kind)` preserves stream/JSON contracts, request cancellation and local security checks. `GET /api/backend` exposes only backend identity/readiness and the learning WebSocket address.

- [x] Bound uploads before forwarding; preserve response status, no-store headers and speech/chat error shapes.
- [x] Distinguish backend startup failure from Ollama offline or Whisper missing.
- [x] `npm start` and `npm run dev` supervise Python plus Next.js; reuse only a healthy, identified June backend and stop only children owned by that supervisor.
- [x] Test stopped backend, oversized uploads, cross-origin requests and stream cancellation through the real bridge.

## Task 5 — Phase 4 learning studio and presentation

**Create:** `components/PhaseFour.tsx`, `app/learn/phase-4/page.tsx`, `backend/examples/basics.py`, `backend/examples/async_status.py`, `backend/examples/june-python.ipynb`, `docs/phase-4.md`.
**Modify:** chat/version labels, metadata, README and scoped learning-page CSS.

- [x] Follow the workbook order exactly: Python basics → pip/environments → Jupyter → async Python → FastAPI/WebSockets.
- [x] Show readable examples and a live, cancellable WebSocket model demo. Keep the normal chat on its existing streaming transport.
- [x] Explain which parts run in the browser, Next.js, Python, Ollama and Whisper; leave Jupyter installation optional for later learning.
- [x] Preserve the orb, voice controls and warm dark/teal design; use responsive layout, keyboard controls, plain text and reduced motion.
- [x] Verify the learning page on desktop and mobile and confirm navigation releases its socket/request.

## Task 6 — Verification and local delivery

**Create:** `backend/tests/test_backend.py`, `docs/verification-v0.3.5.md`.

- [x] Run Python focused tests, existing Node regressions, TypeScript checking and the production build.
- [x] Run actual HTTP and WebSocket Qwen requests; check streamed chunks, follow-up context, Stop and recovery.
- [x] Run a speech fixture through the new Python endpoint; check cancellation and cleanup independently of human microphone availability.
- [x] Inspect the rendered desktop/mobile chat and learning studio and capture screenshots inside the project.
- [x] Record measured timings, checks and any unavailable physical voice verification. Do not mark a voice conversation verified from a synthetic fixture.
- [x] Commit the local branch after checks. Do not push, publish or change unrelated roadmap progress as part of this local upgrade.

## Acceptance

June opens at the same address, genuine replies and local transcription pass through Python, cancellation frees resources, failures are actionable, and the Phase 4 studio matches the roadmap. The delivery lists observed evidence and any remaining human microphone step rather than promising the absence of all bugs.
