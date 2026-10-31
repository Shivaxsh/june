# June v0.3 verification

Branch: june-v0.3. development branch Local application: http://127.0.0.1:3001. Voice studio: /learn/phase-3.

## Passing checks

- TypeScript and production compilation passed; 21 focused tests cover the previous media lifecycle and new voice controllers.
- Real browser voice list offers Samantha (American English) and other known local female English voices. No recognised local female Indian English voice was present. No male/unknown/remote voice is used as a fallback.
- Samantha preview started real synthesis, with speaking state, captions and a labelled visual approximation. Actual browser word-boundary events were observed on spoken model replies.
- Real Qwen typed requests produced streamed text and automatic spoken answers. Hear reply, Stop voice and muting during replay worked; the orb returned to idle immediately.
- A Karen voice choice, American recognition language and disabled automatic speech survived reload. Defaults were restored to Samantha, Indian recognition English and automatic speech enabled afterwards.
- The sentence-streaming learning demo spoke while demonstration text was still arriving; Stop voice cancelled playback while the text stream continued. This is labelled demonstration text, not a model response.
- New chat cancelled recognition and reset the orb/context. Keyboard Space activated and released push-to-talk. The toggle provides an alternative to holding a key/pointer.
- Mobile chat and studio at 390 × 844 had scrollWidth 390, with no horizontal overflow. Desktop checks use 1280 × 900.
- Still view follows the same reduced-motion branch used in Phase 2. Speech amplitude is explicitly unavailable; no fake waveform appears in the meter.
- Local chat API contracts and Phase 0 static files are unchanged. Only voice/language/mute settings persist; transcripts/conversations do not.

## Recognition limit — real voice conversation not completed

The embedded browser advertises recognition and reached a listening state, but its recognition service subsequently returned a network error and produced no dictated transcript. Only the in-app browser is available to automation on this host; no separate Chrome/Safari browser control was configured.

Consequently the physical sequence speak -> review -> send -> spoken answer could not be verified. Controller tests verify interim/final replacement, transcript edits, draft merging, denied/unsupported recognition, startup timeout, release before delayed startup, cancellation and stale result rejection. These simulated tests do not substitute for genuine dictated input.

Phase 3's build checkbox is deliberately not marked complete. Current progress is exported unchanged. A browser with a working recognition service is needed to finish that acceptance check; typing with spoken answers is available now.

## Review and recovery

Source self-review performed; no independent review tool was available. A sentence-buffer issue that delayed a complete sentence until the next word was corrected and covered by a test. Browser audio requires a deliberate interaction; failed/blocked playback shows Preview voice/Hear reply instructions. Stop, mute, source changes, navigation and hidden tabs invalidate queued speech and recognition events.

The Next.js parent-lockfile warning remains harmless: the parent lockfile is outside this separate repository. No speech providers, API keys, hardware purchases or paid services were added.

## Final delivery evidence

Final production build/typecheck passed after the sentence-buffer correction. A final real Qwen typed greeting produced a Samantha spoken reply and captions; Stop voice restored idle. Chat and studio screenshots are saved outside Git in Documents. Fresh progress export confirmed p3-b is false and was copied unchanged, including other progress and personality answers.
