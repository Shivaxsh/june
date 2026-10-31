# June v0.4 — Phase 5 implementation plan

Approved scope: explicitly enabled local hands-free conversation, automatic sending, “Hey June” wake/interruption, 30-second follow-ups, existing Qwen/Whisper/female system voice, no accounts or purchases.

## Tasks

- [x] Compatibility: verify Pipecat 0.0.85, ONNX Runtime 1.23.2, Vosk 0.3.44 and NumPy 1.26.4 in an isolated environment before changing the runtime lock. Add repeatable setup, verified model download and readiness.
- [x] Backend: a bounded local `/ws/voice` Pipecat pipeline for wake/VAD/Whisper; single session, 30-second utterances, silence endpointing and cancellation. Preserve existing APIs. Add `/api/voice/status`.
- [x] Browser: continuous resampling/PCM streaming, explicit consent, bounded socket buffering and cleanup; numbered sessions/turns reject stale events.
- [x] Integration: reuse chat submission/context and speech queue; preserve typed draft and manual review; wake phrase interrupts all old work; playback completion starts follow-up window. Honest orb and microphone labels.
- [x] Learning: seven workbook topics, live diagnostics, labelled WebRTC loopback demo, walkthrough and responsive presentation.
- [ ] Verification: new focused tests, existing regressions, TypeScript/build, real engines, browser checks, screenshots and local commit. Human microphone verification is required before changing the Phase 5 build checkbox or exporting completed progress.

## Defaults and interfaces

- Branch `june-v0.4 development branch`; current checkout and local port 3001; backend 8001; Ollama 11434.
- Browser captures PCM16 mono at 16 kHz in 20 ms packets. Maximum binary frame 4096 bytes, queued audio 2 seconds, JSON control 32 KB. A congested/disconnected transport stops visibly rather than dropping a question silently.
- Voice socket: browser sends `start`, `activity`, `cancel-turn`, `ping`; server sends `ready`, `state`, `wake`, `transcript`, `error`, `pong`, `metrics`. Every turn-bearing event includes the server session identifier and monotonic turn number.
- Browser remains the source of chat history and calls the unchanged `/api/chat` for accepted transcripts. The Python pipeline owns audio boundaries and transcription; browser playback state feeds the follow-up timer. No second conversation store.
- Short/normal/patient silence: 0.8/1.5/2.5 seconds; minimum voiced speech 0.5 seconds; maximum recording 30 seconds; first-question timeout 10 seconds; follow-up 30 seconds after playback ends. Wake detector keeps bounded pre-roll so a combined wake/question is retained.
- Stop/New chat/hidden page/navigation/source takeover release the microphone and cancel all active work. No automatic rearming after reconnect/reload.
- Restricted local Vosk grammar includes `[unk]`, not just the desired phrase. Written replies remain unchanged; hands-free synthesis substitutes “my wake phrase” for “Hey June”.
- Vosk small English model assets stay outside Git in June's existing application-support area. Logs do not contain audio or transcript text.

## Review focus

Resource ownership during late microphone grants; stale transcript/playback callbacks after interruption; self-activation from synthesis; unbounded audio/control queues; preserving draft/history on voice failures; session lock release on disconnect and engine failure.

## Delivery status

Implementation and automated verification are complete. Independent review findings were reproduced and fixed; final bounded re-review reported no findings. Human microphone conversation, follow-up and real speech interruption remain the explicit completion gate. Phase 5 roadmap build and completed progress export remain unchanged. See docs/phase-5-verification.md.
