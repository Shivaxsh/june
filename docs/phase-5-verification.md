# June v0.4 — verification record

Date: 15 October 2026. Intel Mac, macOS 15.7.9, Python 3.12.5. Branch `june-v0.4 development branch`. Public v0.0 site untouched.

## Automated checks

- 55 JavaScript/TypeScript unit regressions passed, including continuous 16/44.1/48 kHz resampling, above-Nyquist filtering, bounded worklet queues, duplicate/stale transcript rejection, socket congestion, delayed permission, denial cleanup, unsupported capture, cancellation and wake masking in spoken text only.
- 42 Python regressions passed, covering existing HTTP/chat/speech contracts plus voice boundaries, patience, 30-second capture cap, 30-second follow-up expiry, empty wake/transcripts, interruption, stale playback feedback, single ownership, oversized packets, missing assets, local origins and disconnects during startup.
- Independent review reproduced three issues; regression tests were observed failing before fixing them: retained voiced pre-roll, disconnect monitoring during initialization and cleanup after failed transcript delivery. Further wake-only regressions preserve the original first-question window and retain a bounded pending question during slow wake transcription. The deadline applies to question onset.
- TypeScript check passed. Production build passed; final rebuild after the last interface label correction also exited successfully.
- Pinned Pipecat 0.0.85, ONNX Runtime 1.23.2, Vosk 0.3.44 and NumPy 1.26.4 imported and ran actual CPU inference in an isolated environment, then were installed into the active locked backend environment. Repeat setup completed successfully. Initial native library loading after installation took several minutes; later process/session startup was much faster. No performance promise is based on cold installation.

## Actual engine and transport measurements

These are small **synthetic audio fixture** checks, not a human accuracy benchmark.

| Check | Observed result |
| --- | --- |
| Wake recognition, Nicky and Samantha fixtures | 2/2 detected; wake event at 1.34 s into each file |
| Negative ordinary speech | 0 activations across 2 clips |
| Silence and seeded low-level noise | 0 activations across 2 × 8-second clips |
| Actual Silero confidence | Reached 1.0 on speech; silence probe below 0.2 |
| Pipecat → Whisper combined wake/question | 7.175 s including paced audio; Whisper 2.664 s |
| Live `/ws/voice` → Whisper | Session ready in 3.86 s; first transcription 3.140 s |
| Live accepted transcript → streamed Qwen | First text 1.06 s; total 1.45 s; 7 deltas; correct Tokyo answer |
| Follow-up without wake phrase | New turn accepted; Whisper 1.416 s |
| Wake during reported speaking activity | Old completion ignored; replacement turn transcribed in 1.724 s |

Playback feedback in the socket fixture was simulated. Separately, the real browser produced a genuine Qwen “Hello!” reply and a Nicky synthesis **speaking** event with honest amplitude-unavailable labeling. This does not prove that a human heard and interrupted the complete hands-free sequence.

Diagnostic logs and generated audio fixtures are ignored under `.june-work`; runtime services do not log their transcript contents. The official 41,205,931-byte Vosk archive matched SHA-256 `30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498`.

## Browser checks

- Separate verification tab used; original user chat and roadmap data preserved.
- UI shows v0.4 / Phase 5, local readiness, explicit microphone enablement, patience selector and Nicky’s actual American English label.
- Typed local chat, streamed reply and Hear reply triggered actual synthesis playback events.
- Learning studio follows all seven topics. WebRTC data-channel loopback delivered its text between two peers and Stop released the demo connections.
- Learning layout checked at 1280 px and 390 px, with screenshots. The chat also reached genuine microphone waiting mode with changing measured levels, then Disable hands-free returned it to microphone-off and released the backend session. No human speech was supplied in that browser check.
- Browser-control tooling reported unrelated telemetry connection errors; those were not June application requests.

## Human verification gate — pending

A real microphone conversation including follow-up and “Hey June” interruption has **not been confirmed**. The user has been asked to perform it. No Phase 5 build completion checkbox or completed progress backup has been changed.

Still required: enable hands-free; say a wake phrase plus question; hear June’s selected female voice; ask a follow-up during the window; interrupt actual speech with “Hey June”; verify Stop releases the microphone. Record missed wakes and accidental activations in the real room. Physical mobile-device and varied-accent accuracy are unverified.

## Final checks

- Final TypeScript and production build completed successfully; updated production app is running on 3001 with Python on 8001 and the existing Ollama on 11434.
- Final transport smoke check passed again after all turn fixes: ready in 3.90 s; Whisper 1.551 s / follow-up 1.461 s / replacement 1.332 s. The Qwen cold response took 10.67 s to first text and 11.06 s total, versus the earlier warm 1.06 s / 1.45 s. These differences reinforce that latency is variable.
- Desktop chat (1280 px), mobile chat (390 px), desktop/mobile learning screenshots captured in ignored `.june-work/phase5-*.png`. Both measured chat widths matched their scroll widths; mobile was exactly 390 / 390 px, with no horizontal overflow.
- Browser keyboard Enter submitted one user/assistant pair; Shift+Enter inserted a line break; Stop restored idle. Literal script text appeared as ordinary text and created zero script elements inside messages. Still view kept a readable state label; New chat cleared the verification conversation.
- Browser console inspection returned no warnings/errors for the final chat. Browser viewport override reset; microphone left disabled; backend reports `busy: false`. Original user chats and roadmap data were not reset.
- Independent final re-review reported no findings in the pending-question capture and ownership fixes. Redundant inherited Python tests were consolidated: final suite has 42 distinct tests, all passing.
- Full human spoken conversation and physical mobile-device verification remain pending. No build checkbox or completed progress backup was altered.

The final regression sweep exposed a timing-dependent existing timeout test: its child could be terminated before writing a PID file. The test now observes the actual spawned subprocess directly and still verifies process exit, slot release and temporary-directory deletion. No speech-service behavior was changed for this test correction.

## Interruption repair — 17 October 2026

- Final repair regressions: **59 JavaScript tests and 64 Python tests passed**. TypeScript and the production build succeeded. Independent review findings were reproduced and addressed, including PCM sample alignment, short utterances, task ownership, sentence-end races and GPU suffix identity.
- The actual local pipeline reproduced the odd-byte WAV failure before the fix, then accepted an ordinary-speech interruption without a wake phrase. Whisper correctly produced 5060 in 1.797 s; a local Qwen confirmation retained it. Playback feedback in this transport test was simulated.
- Actual browser microphone retry: synthetic speech through the Mac speakers triggered wake detection, produced the question, and began Nicky playback. The native pause acknowledgement initially failed because it was checked synchronously; bounded asynchronous acknowledgement fixed that test failure.
- The updated browser then paused actual playback and accepted “5060, not 3060” without a wake phrase. Microphone transcripts are not retained in application logs. This was an acoustic test with synthetic speech, not a controlled human accuracy benchmark. Other audible conversation in the room was also captured while hands-free remained enabled.
- A model refusal to repeat an already-supplied number was reproduced. The per-turn prompt now distinguishes repeating the user's identifier from knowing current product facts. Real API checks returned “You said 5060.” (3.69 s) and “You said 5070 Ti.” (2.87 s). The browser returned “You said 5060.” in 2.6 s.
- Disable hands-free and the global Stop control both returned the actual UI to microphone-off. Backend status subsequently reported `busy: false`. A typed draft remained unchanged through the acoustic interruption. New chat cleared the separate test conversation. Enter submitted once.
- Desktop 1280/1280 px and narrow 390/390 px client/scroll widths matched. Still view remained accessible and displayed its reduced-movement label. Screenshots: ignored `.june-work/voice-fix-desktop.png` and `voice-fix-mobile.png`. Viewport override reset.
- June remains local on port 3001. No public static-page changes, purchases, new commercial requests or model training were introduced.
- Human microphone follow-up/interruption verification is still pending. Phase 5 completion and the completed progress backup remain unchanged.

An additional hour of visible, audible conversation testing was requested after this repair. Its run starts at 08:53:22 UTC on 17 October and is tracked separately; it must not be reported as a completed hour before 09:53:22 UTC.
