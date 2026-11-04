# Interrupted follow-up repair — 2026-11-04

The recent saved conversation contains a completed approved-name response, then `Keep it short.` with an empty stopped reply, followed by another microphone transcript whose answer was also stopped. This confirms the follow-up text arrived; it does not establish whether the subsequent audio was intentional speech, background speech or misrecognition.

A deterministic reproduction found that native input cancelled a generating answer after only 180 ms of positive detector input, before transcription validated any replacement utterance. Empty or uncertain audio could therefore destroy the pending answer. This failure mode is consistent with the observed stopped replies; no historic acoustic recording is available to prove its source.

## Repair

During native model generation, capture a bounded candidate utterance and validate it through the existing transcription service before advancing the turn or cancelling the pending model request. Silence, empty output, rejected low-confidence input and playback echo do not replace it. A valid replacement advances ownership once, cancels the old request, and delivers its transcript. New wake turns, Stop and session cleanup invalidate/cancel late candidates. Candidate buffers remain bounded to 30 seconds.

During actual playback, the existing sustained-speech interruption remains prompt. If output starts while a candidate is being captured, the buffered beginning transfers into the normal interruption capture instead of dropping the first words. This cannot distinguish a nearby person's intelligible speech from intentional user speech, and is not a claim of perfect room-audio rejection.

## Verification

- Six new regression cases: empty noise preserves generation; a validated replacement is submitted once; playback still interrupts; transcription rejection preserves generation; stale decoding after a new wake is ignored; beginning retained when output starts mid-candidate.
- Full Python suite: 346 passed. One earlier full run hit the existing 2-second native worker startup test timeout; its five tests passed alone, and the final full run passed in 24.348 seconds without modifying that timeout.
- A real temporary `/api/chat` call using the recent approved-name response and `Wait, keep it short.` completed with `Shivansh.`. First text: 12.289 seconds; total model response: 14.972 seconds. No new live conversation or memory was saved by this check.
- That generated answer was then sent through the fixed saved June voice and native playback. Events included accepted/start/boundary/end, without error or cancellation. Request to first playback event: 8.592 seconds; end: 9.534 seconds. This used 9 more input characters within the existing 1,500-character validation cap.
- These separate real model/output checks and simulated-detector regressions do not constitute a human microphone acceptance pass. Browser diagnostic access was unavailable in this session (`browser.user is unavailable`); no microphone was enabled by the test.

This fixes premature generation cancellation, not slow inference or variable cloud synthesis latency. Background speech that transcribes confidently can still be treated as a new utterance. The new cloud-voice room/interruption acceptance gate remains open until confirmed in normal use. No voice identity, model selection, approved memories, chats or published sites changed.
