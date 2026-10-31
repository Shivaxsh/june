# June v0.3.1 — local speech repair verification

Date: 13 October 2026 (Asia/Kolkata). Branch: `june-v0.3-voice-fix development branch`. App: http://127.0.0.1:3001.

## Root cause and repair

The previous browser SpeechRecognition instance returned a network error. Direct getUserMedia capture worked on the same browser, isolating the broken dependency to its external recognition service. Its internal provider configuration was not established. Production input now records directly and uses local whisper.cpp v1.9.5 with base.en, so it does not depend on that service.

## Automated and real-engine checks

- TypeScript and production build passed. 39 tests passed, no skips in this installation. Existing speech/media tests remain; new tests cover WAV encoding/validation, quiet/short/malformed/oversized/rate/channel inputs, direct recording without vendor recognition, editable transcript retention, early release, repeated capture, permission errors/timeouts, stale callbacks, blocked audio startup while permission is pending, job cancellation, silent worklet output and configuration consistency.
- Real base.en inference (not simulated replies) transcribed the official JFK speech fixture. Setup verified the model SHA-256 against official LFS metadata and saved readiness only after this smoke transcription succeeded.
- The server API returned the expected sentence from the 11-second reference WAV in **2.494 seconds of server work / 2.510 seconds total HTTP time** on this Intel Mac. Subsequent test runs also used the real engine.
- A real concurrent engine request was rejected as busy. A controlled child-process failure and compressed watchdog test also verified timeout escalation, termination of a child ignoring SIGTERM, deletion of temporary audio and release of the job lock. Aborting a real engine job allowed a subsequent job to complete; the temporary speech-directory list matched its starting state afterwards.
- Foreign Origin was rejected with HTTP 403; non-WAV content type with HTTP 415. Streaming body limits are enforced even without a Content-Length header. Requests pass only fixed local model/file arguments to the executable, with no shell.
- A stopped-server network failure now produces restart/refresh instructions instead of an unhelpful generic fetch error. Setup reads the same ignored .env.local configuration as the app.

## Browser checks

- Updated app reports local Whisper ready, with recording enabled. Microphone access succeeded in the embedded browser; actual recording meter readings changed with captured audio. Local transcription returned editable words from that capture. The accuracy of this uncontrolled room recording was not independently established.
- Mouse hold-to-talk and keyboard Space hold/release both entered local transcription. Cancel transcription returned the orb and controls to idle immediately. Quiet/no usable speech produced a clear retry message.
- Real Qwen streamed a typed arithmetic question and answered correctly. Observed first text 7.5 seconds / total 7.7 seconds for this request; this is an example, not a performance promise.
- Samantha (American English) replay and preview produced actual synthesis start/boundary events and captions. Stop voice restored idle. No recognised local female Indian English voice was available in this browser.
- Muting during Karen preview immediately stopped playback. Karen and mute preferences survived reload; the original Samantha selection and enabled automatic speech were restored afterwards. Reload cleared only the separate verification chat.
- Chat and learning studio fit desktop 1280 × 900 and mobile 390 × 844; document scrollWidth matched viewport width. Screenshots were visually inspected. Still view uses the orb's reduced-motion branch and retained labels and measured input levels. No amplitude is invented for synthesis.
- Updated learning studio follows all six topics and explains local recording/transcription and optional browser/hosted alternatives. Browser error logs checked during the local chat test were empty.
- Existing user chat was not reloaded or cleared. Phase 0 HTML/CSS and the Pages/main branch are unchanged.

## Privacy, limitations and acceptance gate

Production speech uses only the loopback transcription endpoint. No browser SpeechRecognition constructor is used by the production hook; no commercial speech API is configured. WAV and transcript output use a private temporary directory that is removed after success, error or cancellation. Client buffers are discarded; no conversation/transcript persistence was added. Only existing voice/mute preferences persist.

Permission denial, unanswered/late permission, unavailable runtime and failure races have automated coverage; those device/browser error conditions were not physically forced by revoking this user's working microphone permission. The two-minute engine timeout is enforced but was not deliberately allowed to consume two minutes in a physical browser test. Touch interaction was reviewed for shared pointer handlers, not tested on a physical phone. Whisper can mishear background noise and accents; editable review is required.

**Remaining acceptance step:** the user must dictate a known request, confirm the transcript is correct, use it, send it to local Qwen and hear the selected female reply, then stop playback. A request for this human check was presented after the app was ready. Automated fixtures, typed requests and uncontrolled room capture do not establish that complete human sequence. Phase 3 build stays unchecked until it succeeds.

Fresh progress backup: `/Users/apple/Documents/June-v0.3.1-progress.json`. Comparison before/after roadmap reload showed identical progress and character data, including p3-b false. Roadmap and workbook phase/topic counts are aligned, with all existing checkbox indices preserved.

## Delivery evidence

Screenshots live outside the public repository:

- June-v0.3.1-chat-desktop.png
- June-v0.3.1-chat-mobile.png
- June-v0.3.1-learning-desktop.png
- June-v0.3.1-learning-mobile.png

Self-review checked the recording/server boundaries, cancellation, source ownership, safe text rendering and privacy. No independent reviewer tool was available. The existing Next.js warning about an unrelated parent lockfile is informational; it was not changed during the voice repair.
