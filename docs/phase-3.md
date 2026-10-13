# Phase 3 — June gets a voice (v0.3.1)

June: http://127.0.0.1:3001 · learning studio: /learn/phase-3.

## One voice request, step by step

1. Hold to talk or Start listening deliberately asks for microphone access.
2. AudioWorklet captures mono PCM in browser memory. Its output is silent: the microphone is never echoed to speakers. The actual sample RMS drives the recording meter and orb.
3. Release / Stop listening flushes the last samples, stops tracks and closes the audio graph. OfflineAudioContext resamples from the microphone's native rate to 16 kHz. A shared helper encodes PCM16 WAV and checks its duration/volume.
4. The browser sends WAV only to `/api/speech/transcribe` on this Mac. Next.js validates it and launches pinned whisper.cpp with local base.en. There is no vendor speech-service request or API key.
5. A temporary private directory holds the recording and engine output. Completion, failure, cancellation and timeout remove it. The recogniser returns text for editing; Use transcript appends it to the existing draft. Send remains separate.
6. The existing chat route sends reviewed text and June's prompt to local Qwen. Complete reply sentences enter a speech queue while remaining text arrives.
7. An explicitly chosen local female English voice reads them. Text remains visible; fenced code is excluded from speech. Playback start/end/boundary events drive captions and a labelled visual approximation.

## Learn in the same order as the workbook

1. **Web Speech:** learn recognition versus synthesis. Browser recognition may depend on an online service; its network error prompted this repair. June now uses Web Speech only for local synthesis.
2. **Speech to text:** inspect `lib/voice/capture.ts`, `public/audio/recorder-worklet.js`, `lib/voice/pcm.ts`, `lib/voice/local-recognition.ts`, and `lib/server/speech.ts`. Understand recording, resampling, WAV, local inference and editable review. This English-only model supports English input; selecting an accent does not create a different recogniser.
3. **Text to speech:** inspect `lib/voice/speech.ts`. Compare the text model's answer with the separate speaking engine. Ordinary pitch is 1; default rate is 0.98.
4. **Sentence streaming:** inspect `lib/voice/sentences.ts`. Complete sentences preserve order; successful completion flushes the final fragment. Request and utterance tokens reject stale work.
5. **Orb and captions:** inspect `lib/orb/state.ts` and `components/orb/Orb.tsx`. Actual listening and speech lead generation and previews. Captured microphone levels are measured. System speech has no exposed waveform, so its motion is explicitly approximate.
6. **Female voice selection:** inspect `lib/voice/voices.ts`. Wait for voiceschanged, filter known local female English identities, prefer Indian English and label the actual fallback accent. Save selection and mute only. Unknown/male/remote voices never become automatic fallbacks.

## Cancellation and source ownership

Start recording cancels speech and Phase 2 media. Starting sample/file playback or speech preview cancels recording/transcription. Send is disabled during recording/transcription, but typing stays available. Recording is disabled during model generation. Stop and New chat cancel generation/recording/transcription/speech; Stop voice leaves text generation running. Hiding/leaving the page stops active media work; nothing restarts automatically. A cancelled permission request stops tracks if permission arrives later.

Pending access times out after 15 seconds; recordings stop at 30 seconds. Transcription runs with two CPU threads, one job at a time, a 120-second server timeout and a slightly longer client timeout. A missing engine/model or empty transcript produces an actionable error and retains the existing edited transcript. No transcript or conversation is persisted. Old browser recognition language preferences remain harmless and unused.

## Setup

Run `npm run speech:setup`, then `npm run speech:check`. Setup uses the installed compiler and Python, pinned private CMake, official whisper.cpp source, SHA-256-checked base.en and a real reference transcription. The engine, model and setup manifest live outside Git under June's application-support speech folder. It adds no always-on process, global tool installation or paid provider.

Browser recognition is now a learning comparison, not June's production input. Optional hosted providers may charge fees and are not configured. Python foundation remains Phase 4; wake words/continuous conversation remain Phase 5.

## Resources

- [Web Speech](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [Microphone access](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
- [AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)
- [Local whisper.cpp](https://github.com/ggml-org/whisper.cpp)
- [Voice loading](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/voiceschanged_event)
