# June v0.3.5 — verification record

Date: 13 October 2026. Machine: the existing Intel MacBook Pro, 8 GB RAM. Branch: `codex/june-v0.3.5`. Model: `qwen2.5:1.5b`; input: whisper.cpp v1.9.5 / `base.en`; browser output: saved Nicky, American English.

## Automated checks

| Check | Observed result |
|---|---|
| `npm run backend:test` | 22 Python tests passed |
| `npm test` | 44 JavaScript tests passed, including 3 new bridge regressions |
| `npm run typecheck` | Passed |
| `npm run build` | Passed; all chat, speech and learning routes generated |
| `npm run backend:setup` repeated | Existing isolated environment reused; locked dependencies satisfied |
| `npm run backend:check` | Python, local Qwen model and local Whisper all ready |
| `git diff --check` | Passed |

Python checks exercise validation, local settings, malformed/truncated/oversized/invalid-Unicode streams, missing/offline models, split UTF-8, HTTP disconnect before another token, explicit demo cancellation, HTTP/WS origins, nested JSON, WAV errors, duplicate speech jobs, timeouts, repeated jobs and subprocess cleanup. JavaScript checks cover the existing recorder, voice queue, voice selection, captions, orb, media ownership and the new proxy's streaming, cancellation, redirect refusal and bounded input.

The upstream Starlette test client emits a deprecation notice for its HTTPX integration. It did not fail the suite; production uses ordinary HTTPX requests, not that test client. No test result is inferred from a successful build alone.

## Real engine and transport checks

- Genuine HTTP replies worked directly through Python and through the Next.js bridge. A fresh model question returned Germany; a follow-up returned Berlin using the prior answer as context.
- Longer explanations arrived as separate text events. The browser WebSocket lab displayed a completed, genuine response with **40 text events**.
- Closing a running HTTP reply allowed a subsequent arithmetic reply. Cancelling the WebSocket lab restored its input and Run control.
- The upstream `jfk.wav` speech fixture was canonicalised to June's WAV contract and transcribed by the actual installed Whisper engine through Python and the bridge. Recognised text included the expected country sentence.
- One observed bridge transcription took **1,883 ms**. A later cancellation/recovery check took **2,130 ms** for the retry. These are measurements of that fixture on this Mac, not promises for every recording.
- Aborting an actual bridge transcription after 400 ms allowed another recording to complete with HTTP 200. Temporary speech-folder contents returned to the baseline after the retry.
- The browser chat retained the favourite-colour fact across a follow-up. Observed written reply times were approximately 1.2–1.4 seconds, with first text after 0.6–0.9 seconds in those checks.
- Stopping Python left the separately supervised web app available. Model status returned `offline`, speech status returned `error`, and chat returned HTTP 503 with the actionable Python restart message. No simulated answer was substituted.
- Terminating the supervisor stopped its owned Next.js and Python listeners; Ollama stayed running. A fresh `npm start` brought both June services back.
- Loopback binding was confirmed for ports 3001, 8001 and 11434. Mad Realm's existing port-3000 process remained running.

## Browser checks

- Rendered chat and learning studio inspected at desktop widths and at **390 × 844**. Each page had a document width of 390 with a scroll width of 390; no horizontal overflow was observed.
- Enter submitted one real request; Shift+Enter produced a newline without sending. Blank draft kept Send disabled.
- Nicky remained selected, and Speak replies remained enabled. Replaying a reply produced actual browser speaking events and word-event captions; Stop voice returned the orb to idle.
- Still view displayed its reduced-movement label. The operating system's reduced-motion preference was not changed; the existing CSS/reduced-motion handling was preserved.
- New chat cleared the separate verification conversation. The user's original open conversation was not reloaded or cleared.
- The WebSocket studio's completion, Stop and navigation cleanup were exercised. No browser console errors were observed in the inspected tabs.
- Screenshots are saved in the ignored project folder `.june-work`: `phase4-chat-desktop.png`, `phase4-chat-mobile.png`, `phase4-learning-desktop.png`, `phase4-learning-mobile.png`, and `phase4-learning-preview.png`.

## Defects found and repaired

1. A polling disconnect watcher could swallow cancellation and hang an invalid upload. Replaced it with a direct ASGI disconnect wait and middleware that preserves the receive channel. Invalid WAV requests now return promptly.
2. Fixed-size upstream reads delayed short streamed replies. Reads now forward incoming chunks without waiting for a larger buffer.
3. Added refusal of backend HTTP redirects, readable errors for deeply nested JSON, and UTF-8 validation before yielding model text, following the independent code review.
4. Added bounded connection/reply waits in the learning WebSocket interface and graceful rejection of binary socket frames.

## Practical limits

The human sequence “speak into the microphone → review → Send → hear June” was **not repeated with live human speech during this migration**. The unchanged browser capture/review layer passed its regressions, the new transcription route passed real speech-fixture and cancellation checks, and browser playback events were observed. Physical microphone and acoustic voice quality should not be described as newly verified here.

Qwen remains a small pretrained model and can give incorrect or awkward answers. Moving its connection into Python changes architecture, not its underlying intelligence. Conversations still clear on reload; permanent memory, account tools and home control are later phases.

No public deployment, paid integration, hardware purchase, progress-checkbox change or personality-answer change was performed for this local upgrade.
