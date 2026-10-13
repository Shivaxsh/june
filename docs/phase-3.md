# Phase 3 — June gets a voice

June v0.3 runs at http://127.0.0.1:3001. The voice learning studio is /learn/phase-3; the Phase 2 studio remains available.

## The flow

Browser microphone -> browser recognition service -> reviewed transcript -> the existing local chat API -> local Qwen model -> sentence queue -> local female system voice.

The model and synthesis use the local computer. Browser recognition may use an online speech service. June does not save raw recordings or transcripts, and its own server has no speech-upload endpoint. Preferences are the only voice data saved in localStorage: voice identity, recognition language and automatic-speech setting.

## Read these pieces in order

1. `lib/voice/voices.ts` handles delayed browser voice lists, voiceschanged, local female English filtering and saved selection. Web Speech exposes no gender field, so unknown voice identities do not become defaults. The selector labels the voice's language/accent.
2. `lib/voice/recognition.ts` manages a recognition instance and its lifecycle. A 10-second startup timeout, 30-second listening limit and 4-second finishing timeout avoid stuck UI. Releasing while permission is pending stops recognition as soon as it starts; cancellation invalidates late results.
3. `lib/voice/sentences.ts` buffers completed sentences, preserves decimals/basic abbreviations across chunks and removes formatting/fenced code from spoken text. A final fragment is emitted only after successful model completion. The transcript merge helper preserves existing typed text.
4. `lib/voice/speech.ts` owns the sentence queue and one utterance at a time. Every request and utterance gets a token; late start/end/boundary events cannot restart stopped audio or affect the next sentence. Startup and playback watchdogs show useful errors.
5. `components/voice/useVoice.ts` connects the browser controllers to React, persists optional settings, and stops work on hidden tabs/navigation/unmount. It coordinates with the existing audio controller.
6. `components/voice/VoicePanel.tsx` provides pointer/keyboard push-to-talk, a toggle alternative, editable transcript review, voice preview and cancellation. The chat sends reviewed words only when the user chooses Send.
7. `components/Chat.tsx` forwards model deltas into the speech buffer before completion. Stop cancels both model and voice; Stop voice suppresses the speech queue without cancelling text generation. Completed answers have Hear reply.

## Orb and captions

Actual listening has first priority, actual speech playback second, generation third; explicit visual previews and remaining audio activity follow. Word-boundary events highlight the active word when present. Otherwise a timer started only after the real speech-start event approximates caption position. That approximation is labelled.

System speech synthesis exposes no waveform to the Canvas meter. The separate speech-activity ref drives a modest visual pulse; the meter is hidden and amplitude is labelled unavailable during speech. Still view respects reduced motion, retaining the label and captions. This visual pulse is never called measured loudness.

## Ownership and cancellation

Start recognition -> cancel previous speech and Phase 2 audio. Start sample/file audio -> cancel recognition and the current speech queue. New chat -> cancel all activities, clear transcript/chat and restore automatic orb mode. Mute -> stop speech immediately; re-enabling applies to the next request or manual replay. Navigation/hidden tab -> cancel active voice/media, with no automatic microphone restart.

Voice changes stop current speech rather than mixing voices mid-reply. Refreshing voices updates available options. The browser's selected local voice is assigned explicitly to every utterance; pitch remains 1 and the rate defaults to 0.98.

## Limitations and later options

Browser recognition support does not guarantee its online service works in an embedded browser. A network error occurred in this run, so a genuine dictated transcript could not be verified. A normal browser with a working speech service can be used at the same local URL. No paid-provider fallback is silently selected.

Whisper and other local recognition engines are later alternatives that require their own runtime/model setup. Hosted recognition/synthesis providers are optional and may charge fees. Python migration follows Phase 4; always-listening conversation and interruption follow Phase 5.

## Resources

- [MDN Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [Recognition and browser service behaviour](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
- [Voice list and local service metadata](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice)
- [Voice-list loading event](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/voiceschanged_event)
- [Whisper](https://github.com/openai/whisper)
