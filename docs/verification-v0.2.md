# June v0.2 verification

Implementation branch: june-v0.2. development branch Local app: http://127.0.0.1:3001.

## Passed checks

- TypeScript and production build; seven focused state/media lifecycle tests.
- Real Qwen greeting streamed to the chat; face showed Generating reply during the request.
- Generating reply took priority while a real local WAV was playing. After completion the face returned to Audio playback.
- Stop cancelled generation and restored idle; New chat cleared context and stopped audio. Preview was reset when sending.
- Bundled sample and a local WAV selected with the browser file chooser both played. Actual analyser readings changed (observed up to 63%); pause/resume and Stop recovered correctly.
- Invalid audio fixture showed a supported-file error and idle state.
- Four labelled mood previews and Still view with a static network and sound meter.
- Desktop 1280 × 900 and mobile 390 × 844. Chat and learning page scroll width matched mobile viewport width (390), with no horizontal overflow.
- Canvas progression, actual Three.js particle scene, actual GLSL glow, and manually selected ordinary rendering fallback. No WebGL console errors observed while viewing these examples.
- Switching from the Web Audio lesson to another topic stopped sound and reset the orb.
- Model server stopped deliberately: a send failed with an actionable offline error, restored the draft and reset the face. Model server restarted and reconnected.
- Source review: audio has no recording/upload path. Playback uses the bundled local WAV or a blob URL; microphone input is not connected to speakers. Three.js is imported only by the dynamically loaded learning component.
- Phase 0 static files and both HTTP route contracts preserved.

## Microphone verification limit

Actual microphone permission remained pending in the embedded browser; its browser/OS grant dialog was not exposed by the available browser controls. Pending cancellation was manually verified. Successful capture from the physical microphone could not be verified here.

Focused tests use fake devices to verify permission denial, unanswered-request timeout, permission arriving after Stop, stale rejection after a newer source starts, microphone track release on disposal, measured sample processing, no microphone-to-speaker connection, and file playback resource cleanup. These tests are not a claim of real hardware capture.

The reduced-motion rendering branch was exercised with Still view. System preference changes are wired through matchMedia; the machine's global accessibility settings were not changed. The CSS graphics fallback was selected through the lesson control; physical GPU failure was not induced.

## Review

Source self-review performed; no independent reviewer was available. No model training or voice understanding added. The small pretrained model retains its accuracy limitations. A Next.js warning about ignoring a parent lockfile outside this repository is harmless and does not affect the completed build.

## Completion evidence

Final production greeting completed after the model restart. Roadmap exports compared: only p2-b changed to 1; all learning progress and character answers matched exactly. Reload confirmed persistence. Screenshots and progress backup are saved outside public Git in Documents.
