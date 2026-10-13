# Phase 4 — Python, the language of AI

June v0.3.5 keeps the existing voice interface and moves server-side AI work into Python. No new model is trained in this phase.

## Start June

After first setup, use the same two terminals as before:

```sh
# Terminal 1, in /Users/apple/Documents/June
npm run model:start

# Terminal 2, in the same folder
npm start
```

The second command starts Python and the web app together. Open <http://127.0.0.1:3001>. Control+C stops the processes that this command started. An independently started, healthy June Python backend is reused and is not stopped by the web command. Nothing starts at login.

For first setup or after cloning:

```sh
npm install
cp .env.example .env.local  # Only if .env.local does not already exist.
npm run backend:setup
npm run model:pull
npm run speech:setup
npm run build
```

Python 3.12 is installed on this Mac. The isolated environment is `backend/.venv`, and `backend/requirements.lock` pins every runtime dependency. It is separate from the existing Whisper compiler environment. Neither environment nor AI model files belong in Git.

During development use `npm run dev`. Check the running services with `npm run backend:check`. If the Python port is occupied by another app, choose another loopback port in `JUNE_BACKEND_URL` in `.env.local` and restart June. The default is `http://127.0.0.1:8001`.

## Follow the workbook in this order

### 4.1 Python basics

Open `backend/examples/basics.py`. It shows strings, lists, loops, a function and a class. Run it:

```sh
backend/.venv/bin/python backend/examples/basics.py
```

Change a skill, add a greeting, then explain the result. June's real configuration is a dataclass in `backend/june/config.py`; the model adapter is in `backend/june/chat.py`.

### 4.2 pip and virtual environments

`python3 -m venv backend/.venv` creates the environment. `backend/.venv/bin/python -m pip install -r backend/requirements.lock` installs June's pinned packages there. `npm run backend:setup` wraps those steps. No global pip changes are needed.

### 4.3 Jupyter notebooks

The notebook `backend/examples/june-python.ipynb` contains small Python exercises without personal data or model downloads. Jupyter is optional; it has not been added to June's runtime dependencies. When ready to study notebooks:

```sh
backend/.venv/bin/python -m pip install jupyterlab
backend/.venv/bin/python -m jupyterlab --notebook-dir=backend/examples --no-browser --ip=127.0.0.1
```

Open the local link Jupyter prints. Keep its access token private. Notebook variables belong to the notebook kernel; they are not June's permanent memory. Close the notebook and Control+C its server when finished.

### 4.4 Async Python

Run `backend/.venv/bin/python backend/examples/async_status.py` while June is running. `await` allows other requests to proceed while a network response is pending. June shares one HTTPX client rather than creating a connection pool per token.

`stream_chat` is an async generator: `yield` produces one event at a time. Cancellation propagates into its HTTP context, so Stop closes the upstream stream. `SpeechService.transcribe` owns a subprocess until it exits; cancellation terminates it, waits for exit, removes temporary recordings and frees its job slot.

### 4.5 FastAPI and WebSockets

`backend/june/app.py` defines the endpoints and lifespan. Visit the [Phase 4 studio](http://127.0.0.1:3001/learn/phase-4) for a real WebSocket model request with explicit Run and Stop controls. It creates a fresh temporary conversation and does not alter the main chat.

The normal chat continues using HTTP NDJSON. The WebSocket learning route is an alternative transport, not a requirement for streaming. Both use the same validated messages and model adapter. Browser origins are restricted to June on port 3001; frames are limited, duplicate requests are rejected and disconnect cancels generation.

## Understand one request

1. **Browser:** React collects reviewed text. Voice recording stays in the browser until transcription is requested. The Canvas orb follows real activity.
2. **Next.js, port 3001:** the same-origin API bridge checks origin and size, forwards to Python and passes response chunks back without collecting the entire answer.
3. **Python, port 8001:** FastAPI validates the conversation, adds June's server prompt and opens an async stream to Ollama.
4. **Ollama, port 11434:** the existing Qwen2.5 1.5B model computes the answer locally. Python translates its events into June's unchanged delta/done/error contract.
5. **Browser again:** the written answer appears incrementally. Complete sentences enter the existing browser synthesis queue and use your selected local female voice.

Whisper uses a different path: mono 16 kHz PCM WAV → the same-origin bridge → Python → the existing CPU-only whisper.cpp engine → editable transcript. Speech-output synthesis stays in the browser so its installed voice choice, captions and interruption controls remain available.

## Safety and resource boundaries

- All three servers bind to the local computer; model requests cannot use a remote configured URL. HTTPX ignores proxy environment variables for local inference.
- Chat: maximum 20 messages, 2,000 UTF-16 units per message, 6,000 total, 32,000-byte request body; alternating roles with no client system prompt.
- Model: existing context 4096, reply cap 256, temperature 0.1, thinking disabled; overall timeout 180 seconds.
- Audio: canonical WAV only, maximum 1 MiB and 30 seconds; quiet or malformed recordings are rejected before running Whisper.
- Speech: one active job, two CPU threads, 120-second timeout, fixed executable arguments and no shell interpolation.
- Disconnect and timeout terminate speech before removing its private temporary folder. Recordings, transcripts and conversations are not stored as durable history.
- Python processing improves the architecture; it does not guarantee better reasoning from the same small model.

## Source map

| File | Responsibility |
|---|---|
| `backend/june/config.py` | Local addresses, model and speech paths |
| `backend/june/prompt.txt` | Production system prompt |
| `backend/june/chat.py` | Validated chat, Ollama adapter and explicit demo |
| `backend/june/speech.py` | WAV validation, verified model, subprocess cleanup |
| `backend/june/app.py` | FastAPI HTTP/WebSocket routes and cancellation |
| `lib/server/backend.ts` | Same-origin browser bridge |
| `scripts/backend.mjs` | Environment setup and service health |
| `scripts/start.mjs` | Owned process startup/shutdown |
| `components/PhaseFour.tsx` | Learning studio and live WebSocket lab |

The older TypeScript model/speech modules remain as Phase 1/3 regression references; no production route imports them. Python is the active backend. `scripts/evaluate-models.mjs` now reads the Python production prompt.

## Checks

```sh
npm run backend:test
npm test
npm run typecheck
npm run build
npm run backend:check
```

Python tests use mock model streams and temporary fake speech engines for deterministic cancellation/timeout checks. Existing Node tests cover voice, recorder and orb behaviour; they also retain historical backend contract checks. Real local inference, real Whisper and browser observations are recorded separately in `docs/verification-v0.3.5.md`.

## Primary references

- [Python tutorial](https://docs.python.org/3/tutorial/)
- [Python virtual environments](https://docs.python.org/3/library/venv.html)
- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/)
- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [HTTPX async streaming](https://www.python-httpx.org/async/)
- [Uvicorn settings](https://www.uvicorn.org/settings/)
