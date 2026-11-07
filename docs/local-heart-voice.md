# June’s local Heart voice

The user approved listening candidate C, Kokoro `af_heart`, as June’s speaking voice. It replaces the hosted ElevenLabs voice for previews, streamed replies, replay and hands-free output. Heart is American English. The normal runtime does not instantiate the ElevenLabs provider or send text to a speech service; an old API key in ignored configuration is unused.

## Setup and recovery

Run `npm run voice:setup`, then `npm run build` and `npm start`. Setup downloads the model/voice bank from the kokoro-onnx release and installs pinned dependencies into a separate private Python environment under `~/Library/Application Support/June/voice-lab/`. `JUNE_VOICE_HOME` can override this location. Models and binaries remain outside Git. Python backend dependencies are unchanged. Internet is required for initial setup; synthesis thereafter uses CPU only and requires no account or credits.

The local engine is Kokoro v1.0 (Apache-2.0), via kokoro-onnx 0.6.1 (MIT), ONNX Runtime 1.23.2 and NumPy 2.2.6. The backend still uses its existing NumPy 1.26.4 environment. Sources: https://huggingface.co/hexgrad/Kokoro-82M and https://github.com/thewh1teagle/kokoro-onnx .

## Behaviour

Steady maps the existing expression setting to speed 0.96, exactly the selected sample’s pace. Calm uses 0.90 and Bright 1.02. These are pacing differences, not ElevenLabs emotion tags or a guarantee of emotional acting. The voice ID stays fixed; missing files or errors leave text available rather than choosing another voice. Local Heart has no relationship to a particular actor or the old ElevenLabs voice model.

One persistent worker loads the model once, with two inference threads. Validated text and mono 24 kHz PCM travel through bounded private pipes; generated PCM enters the existing native playback and microphone echo-processing graph. Audio remains temporary. No reference recording or model training is needed for the supplied Heart voice. Captions remain approximate and the orb follows measured playback levels.

Speech requests remain serialized with bounded prefetch. Stop, replacement turns, mute, New chat, navigation and disconnect abort owned streams. Cancelling inference terminates the worker so late audio cannot resume; the next request reloads it. Shutdown reaps it. Readiness starts the model without generating audible speech or opening the microphone.

The original standalone sample C took 10.8 seconds to generate 8.7 seconds of audio on this Intel Mac. This is whole-file generation, not first-audio time or a live conversation benchmark. Local synthesis removes quota/network dependence; it does not guarantee faster full conversations when Qwen and Whisper share the CPU.

## Verification — 2026-11-07

354 Python regressions and 140 JavaScript regressions passed; TypeScript and the production build passed. Seven local-provider regressions cover fixed identity, missing files, old-voice rejection, resident-model reuse, cancellation/restart, malformed output, delayed startup cleanup and background-work priority. Existing native PCM, request ownership, microphone/transcript and sentence-ordering tests remain passing.

In the real browser, Heart preview completed and an approved-name reply was written and automatically spoken through native playback. The screen shows Heart, American English, local-only processing, no credit meter and microphone off. The first run during model warm-up took 24.14 seconds to start preview playback; the name response speech took 27.64 seconds. Foreground voice work now registers with the coordinator, preempts warm-up/extraction and prevents their restart during synthesis. UI explicitly labels speech preparation.

After that change, real local HTTP playback started in 12.644 seconds; Stop was acknowledged in 20 ms and the stream ended cancelled. A subsequent synthesis/reload request started playback in 12.982 seconds and completed in 16.394 seconds. An alternate voice ID was rejected before synthesis. These are observed request-to-playback timings, not promises or microphone-to-answer latency; the Stop acknowledgment is not an acoustic measurement.

Final status reports Kokoro, the fixed Heart identity, cloudText false, no quota object, all local components warm and no active microphone session. No ElevenLabs generation was used. A human speaker-room check with the new voice is still needed to validate physical echo/interruption behaviour; no phase completion or learning checkbox is changed by this delivery. Calm/Bright are pacing presets and have not been approved as emotional acting.
