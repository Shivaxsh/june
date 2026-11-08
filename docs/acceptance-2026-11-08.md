# June reliability acceptance — 2026-11-08

Next phase remains on hold until the room-audio check is confirmed. This report describes bounded checks, not a guarantee of perfect model answers or absence of every possible defect.

## Fresh start and regressions

The app and model server were stopped at the start. Both were launched from the current committed configuration, retaining private data. The browser initially had stale audio errors from the stopped server; Refresh audio and Refresh speech recovered the controls. No API key or hosted voice service is used.

342 Python tests and 140 JavaScript tests passed, including cancellation, stale callbacks, microphone cleanup, permissions, ownership, voice ordering, persistence, retention, imports and invalid requests. TypeScript passed. The SQLite integrity check returned OK. Live memories/profile were not edited by acceptance tests.

## Defect found and repaired

An injected non-object JSON response from the local voice worker raised an uncaught AttributeError. It could escape the PCM producer’s safe error handling and leave playback waiting. A failing test reproduced it before the fix. The provider now validates frame objects and audio field types, reports a safe voice error, retires the damaged worker and permits a clean retry. Regression cases exercise arrays, null, booleans and numbers. All eight focused local-voice tests passed after the repair.

## Real model and memory acceptance

The acceptance script copied SQLite through a read-only connection and tested the private copy. All 29 checks passed: approved name/colour after New chat, database reopen, compound recall, React, async/CPU threading, worker/DOM boundaries, corrected 5060 and 5070 Ti identifiers, honest booking limitations, absent live market data, an async follow-up, fourteen consecutive turns with persistence, current corrections, editing and deleting memories. This is one fixed sample set, not an unrestricted factual-accuracy benchmark.

The first cold React answer took 65.847 seconds to first text. Across non-approved-recall cases the observed median first text was 0.846 seconds; that mixed set includes simple repeat questions and is not a speech-to-answer latency measure. Cold start and shared CPU load remain material limitations. No claim is made that the earlier end-of-speech median 3.5-second / p95 6-second targets pass.

## Audio content and browser checks

Real local Heart audio was generated for a three-sentence explanation of React and web workers. The waveform was non-silent, 7.691 seconds long, and local Whisper reproduced all three sentences exactly (decoder time 5.453 seconds; total generation/transcription check 17.539 seconds). This checks synthesis completeness/intelligibility for that fixture; automatic transcription is not a human judgment of voice quality or room acoustics. The WAV and private diagnostics remain ignored under `.june-work/`.

Browser checks confirmed mute, restoration of Speak replies, blank Enter producing no message, Shift+Enter preserving a newline, one submitted user message, literal rendering of script-tag text, New chat reset and returning to Local AI. Practice mode was explicitly selected for safe-text/keyboard checks and restored afterwards. At a 375-pixel viewport, document width was 375 pixels with no horizontal overflow; the viewport override was reset. A UI Stop attempt reached an already completed practice reply, so it is not counted as a streaming-cancellation success. Real cancellation is checked separately through the native playback API.

## Remaining acceptance

The repaired production build passed and was restarted. Real native playback with audio output enabled started at 9.526 seconds. Stop was acknowledged in 57 ms and the stream ended cancelled; a subsequent request reloaded and completed, starting audio at 16.413 seconds and finishing at 19.782 seconds. Alternate voice identity was rejected. Those are request/playback-control measurements, not acoustic interruption timings.

A real approved-name question was then submitted in the browser with Speak replies checked. It completed in text and native speech, with first audio at 2.78 seconds and last audio end at 5.49 seconds. Hear reply replay also completed (2.35 seconds to first audio, 5.07 seconds total). This illustrates warm short-turn performance but does not establish median/p95 end-of-speech targets. Human quality judgment and a room microphone check remain pending; no microphone was enabled by the agent. Do not interpret synthetic detector tests or PCM playback events as proof of acoustic echo cancellation in the user’s room. Roadmap progress remains unchanged.
