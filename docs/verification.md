# June v0.1 — verification record

Verified on 10 October 2026 on the Intel Mac with 8 GB RAM, using the production
Next.js server at http://127.0.0.1:3001 and Ollama 0.40.2 with qwen3:0.6b.

## Build and code review

- `npm run typecheck`: passed.
- `npm run build`: passed; static chat page plus dynamic chat/status routes.
- `git diff --check`: passed.
- The Phase 0 `index.html` and `styles.css` have no changes.
- Author performed a separate review of request validation, stream buffering,
  cancellation, session reset and configuration boundaries. No independent
  reviewer or automated test framework was used.
- Next.js reports a harmless parent-lockfile warning; it explicitly ignores
  `/Users/apple/package-lock.json` outside this separate repository.

## Manual scenarios

| Scenario | Observed result |
|---|---|
| Blank/whitespace input | Enter produced no message. Send remained disabled for empty input. |
| Keyboard | Enter produced one user message; Shift+Enter inserted a line break. |
| Real model | Greeting, explanatory answers and follow-up text came from qwen3:0.6b. |
| Streaming | A longer explanation visibly grew while Stop was still available. |
| Follow-up context | After stating teal as a test preference, the next reply correctly answered “Teal.” |
| Stop | A running explanation was interrupted; partial text was labelled stopped and input became usable. |
| New chat | Transcript/context reset; cancelling a running demo produced zero residual messages. |
| Reload | Transcript reset to zero messages and mode returned to Local AI. |
| Missing model | Before the download finished, status correctly showed Model missing. |
| Offline runtime | Stopping Ollama produced an offline status and recoverable error; input was restored for retry. |
| Runtime loss during generation | Stopping Ollama while a story was pending produced “The model server disconnected. Restart Ollama, then reconnect.” Controls recovered and mode stayed Local AI. |
| Recovery | Restarting the runtime and reconnecting produced real answers again. |
| Demo mode | Explicitly selected mode showed simulated labels and a fixed practice reply. No automatic fallback occurred. |
| Safe text | `<script>alert("test")</script>` appeared as ordinary text; zero script elements existed inside message bubbles. |
| Responsive layout | Desktop 1280×900 and mobile 390×844 were inspected; long unbroken text wrapped with no horizontal page overflow. |
| Invalid requests | Malformed JSON, system-role input, an oversized message and empty history returned HTTP 400. |
| Origin check | June's own 127.0.0.1 origin was accepted; an external origin was rejected with HTTP 403. |

The initial same-origin check incorrectly used Next.js's normalized request URL.
The fix compares the browser origin to the validated loopback Host header. The
failure was reproduced before the fix and the accepted/rejected cases checked
afterward.

## Observed timing, not a speed guarantee

- Initial short greeting: 4.5 seconds total; first text at 3.9 seconds.
- Final warm greeting: 2.4 seconds total; first text at 0.3 seconds.
- Final single-colour follow-up: 0.9 seconds total; first text at 0.7 seconds.
- A longer explanation took 9.0 seconds in an earlier check.

Runtime logs identify CPU inference and disabled Ollama cloud support. Browser
assets and fetch endpoints are local; server model calls are restricted to
loopback HTTP. Real mode contains no commercial AI provider integration.

## Model limitations

Qwen3 0.6B is a small starter model. It sometimes misinterpreted personal
questions, adopted a user's test preference as its own, or added a word-count
marker. It also gave imperfect technical explanations. The June prompt was
kept concise after checking these behaviours; it cannot guarantee accuracy.
This phase proves the app/model connection, not Claude-level answer quality.

Future phases can evaluate a better model through the same adapter. Conversation
context stays in browser memory for the session; no persistent memory is implemented.

## Delivery

Source is saved on june-v0.1 development branch; main remains the v0.0 Pages publishing source.
Screenshots and progress backups are stored outside the public repository.
Only the Phase 1 build checkbox was changed by this upgrade; existing progress
and personality answers were compared against the preceding export.
