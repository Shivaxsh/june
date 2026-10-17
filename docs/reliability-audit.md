# June reliability audit — 17 October 2026

## Repairs

- **Long chat requests:** the browser previously sent every completed turn, eventually exceeding the server's 20-message / 6,000 UTF-16-unit request contract. It now keeps the newest whole pairs within the budget and shows an explicit context notice. The full written conversation stays visible; this is not persistent memory.
- **Unicode:** shortening an oversized historical reply could split an emoji's surrogate pair and cause an HTTP 400. Compaction now keeps pairs intact. The current user question is never shortened.
- **Length-limited replies:** Ollama's `done_reason: length` now becomes an optional `limited` completion field. Written partial answers remain visible and labelled. Automatic speech keeps complete terminal sentences while discarding an unfinished tail. Existing normal completions keep their contract.
- **Clarifications:** a complete identity-protection clarification does not inherit a misleading truncation warning from the rejected model text.
- **Disconnect race:** a delayed state send could resume after a voice session closed and spawn transcription after cleanup. Capture now rechecks session/turn ownership before starting the engine task. The regression covers both disconnect and a newer wake turn.
- **Stop announcement:** the accessible announcement now confirms Stop rather than retaining “preparing a reply.”

No model weights were trained. The existing local model, speech voice, port, public static site, roadmap identifiers, learning progress and personality answers are preserved.

## Verification matrix

| Check | Result |
|---|---|
| JavaScript regressions | 69 passed, including 42 context parameter combinations |
| Python regressions | 69 passed, including the disconnect race and all three pause settings |
| TypeScript / production build | Passed |
| Genuine streamed cutoff | 256 actual model deltas; completion included `limited: true`; 18.97 seconds total, first text in 1.09 seconds |
| Sample rates | 16,000 / 22,050 / 24,000 / 44,100 / 48,000 / 96,000 Hz; chunk sizes 7 / 128 / 511; output byte-identical across chunking |
| Invalid input | Blank, 2,000/2,001-character boundaries, 1,000/1,001 emoji, invalid surrogate, roles/order, malformed JSON, body/context limits, foreign origins |
| Audio validation | Wrong format, oversized upload, silence rejected; canonical mono 16 kHz PCM speech fixture transcribed through the actual HTTP endpoint |
| Browser long chats | 12 simulated turns and 12 genuine Qwen turns completed; context notice appeared; written messages remained visible |
| Text / keyboard | Literal script text and multiline Unicode rendered as ordinary text; blank Enter did not send |
| Outage / recovery | Ollama stopped deliberately; offline error and typed draft restored; after restart/reconnect the same message received “Hello!” |
| Voice pipeline | Actual Vosk + Silero + Whisper + Qwen; synthetic audio and simulated playback feedback; echo probe resumed and natural interruption preserved 5060 |
| Disconnect cleanup | Actual Pipecat pipeline reproduction now reports no post-close transcription and no pending orphan job |
| Independent review | No additional concrete regressions found in reviewed changes |
| Browser microphone | Speaker-played fixture captured through the real microphone; transcript preserved “5060, not 3060”; appended draft intact; real Qwen replied “You said 5060.” |
| Voice / cleanup | Saved Nicky selection survived reload; preview, captions, replay and active Stop voice passed; navigation released the actual hands-free slot |
| Responsive / motion | 320 px and 390 px had no horizontal overflow; Still view showed reduced-movement label; desktop checked at 1280 px |

The first HTTP fixture attempt correctly rejected a WAV containing extra metadata: June's endpoint intentionally accepts its own canonical browser PCM format. Repacking the fixture to that format passed. This was a fixture error, not a reason to weaken upload validation.

## Model behaviour: a remaining limitation

Fresh controlled cases covered CPU-thread behaviour, three supplied personal facts, correction of an invented role/colour, and exact `5070 Ti` repetition. Twelve limited checks passed across temperatures **0, 0.1 and 0.6**, using seed 42 and a 128-token reply budget.

The synthetic reproduction of the earlier conversation included the model's wrong JavaScript answer and invented project-manager role. The corrected name/project/colour check then failed under all five tested settings:

| Temperature | Seed | Reply tokens | Corrected facts |
|---|---|---|---|
| 0 | 42 | 256 | Failed |
| 0.1 | 42 | 256 | Failed |
| 0.1 | 1 | 256 | Failed |
| 0.1 | 123 | 128 | Failed |
| 0.6 | 42 | 256 | Failed |

A shorter generic prompt also failed the same-history and JavaScript checks, so it was **not adopted**. Runtime temperature remains 0.1. No case-specific factual answer was substituted into ordinary chat.

These are narrow diagnostic cases, not a general accuracy benchmark. More sampling does not establish permanent learning. Acknowledging a correction in one reply does not guarantee applying it in the next. A stronger model should be evaluated against these failures before changing the default; no new model download, paid service or hardware purchase was made in this audit.

## Timing observations

- Canonical HTTP speech fixture: about **1.5 seconds** for local transcription.
- Full synthetic pipeline recheck: startup **3.44 seconds**, Whisper **3.18 / 2.82 seconds**, guarded Qwen number reply **5.18 seconds**.
- Recovered cold model request in the browser: **14.2 seconds** total.

These measurements include different workloads and are not latency promises.

## Evidence and rerunning

Local diagnostic evidence remains under the ignored `.june-work/` directory: `api-matrix.json`, `model-diagnostic.json`, `history-diagnostic.json`, `prompt-diagnostic.json`, `barge-live-results.json`, `ownership-pipeline-green.log`, build/type/test logs and screenshots (`debug-long-chat.png`, `debug-mobile.png`, `debug-desktop.png`). These contain synthetic test cases, not saved user conversations.

Run from the June project:

```sh
npm test
npm run backend:test
npm run typecheck
npm run build
```

The browser connection briefly lost synchronization during navigation; reopening a fresh test tab restored it. The app remained healthy. Temporary viewport overrides were reset.

The existing speech and realtime setup/check commands are documented in the README. Real-device checks must distinguish accepted transcript, generated answer and spoken playback. A fixture passing is not proof of real human microphone performance.

## Completion boundaries

The earlier requested hour-long audible conversation was paused following the user's request to wrap up; it was not completed and is not claimed here. No roadmap build checkbox or completion backup is changed by this audit. Final human acceptance still requires a natural microphone conversation with follow-up and interruption in the user's usual speaker/headphone environment.

A non-blocking Starlette test-client deprecation warning is emitted by the currently pinned dependency stack; test cases pass. Dependencies were not upgraded during this repair.
