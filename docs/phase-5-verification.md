# June v0.4 — verification record

Date: 15 October 2026. Intel Mac, macOS 15.7.9, Python 3.12.5. Branch `codex/june-v0.4`. Public v0.0 site untouched.

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
