# Speaker echo and Phase 6 latency — 21 October 2026

## What the conversation showed

June's spoken GPU enumeration was accepted as the next user message. A clipped
transcript contained one inserted digit and an unfinished final token. The old
echo matcher treated any changed number as a deliberate correction before
checking the otherwise matching enumeration. The resulting automatic request
made June answer her own audio and also enlarged later conversation context.

The model's GPU claims in that exchange are not reliable product information.
This repair addresses audio ownership and latency; it does not train Qwen or
give it live product knowledge.

## Changes

- Recognise a narrowly defined, bare GPU-list echo with two unchanged full
  identifiers and one near-spelled number. Explicit corrections, questions,
  changed suffixes and single-number corrections retain their existing path.
  Accepted user text is never rewritten into a guessed GPU identifier.
- Keep speaking uninterrupted while rejecting the reproduced echo; no new
  VAD-triggered pause or arbitrary silence threshold was introduced.
- Initially request ordinary browser echo cancellation. If the actual microphone
  track advertises the `all` mode, request cancellation of system audio too.
  The optional upgrade wait is bounded at 750 ms; Stop releases tracks and
  ignores late results. Unsupported browsers retain ordinary capture.
- Show the browser's reported echo setting. A setting is not proof of acoustic
  removal. The meaning of `all` comes from the
  [Media Capture specification](https://www.w3.org/TR/mediacapture-streams/#dom-echocancellationmodeenum).
- Skip memory-extraction inference for nonpersonal greetings and questions,
  including request prefixes such as “I wanted to ask…” and “I mean, explain…”.
  Exact personal proposals and ambiguous personal-clause extraction remain.
- Use the same 4096-token runtime capacity for extraction and chat. The old
  extractor requested 2048, causing Ollama to replace its runner before and
  after the background job. This discarded reusable inference state.

No model, selected voice, conversation retention, silence setting or hardware
was changed. Existing chats and pending/approved memory decisions are preserved.

## Measured cause of the slowdown

Sequential real local `qwen2.5:1.5b` calls used the same bounded saved context and
personality. Model runner identifiers and `/api/ps` confirmed replacement when
capacity changed between 4096 and 2048, and retention when it stayed at 4096.

| Controlled case | Before | After |
| --- | ---: | ---: |
| Background extraction of an ordinary technical question | 3.93 s, one inference | 0.4 ms, no inference |
| First text of saved-context answer after that extraction | 16.64 s | 0.085 s with reusable cache |
| First text after a genuine personal extraction, capacity-only comparison | 16.30 s | 0.115 s with reusable cache |

These are controlled samples, not expected response times for every new
question. A warm but changed context still took 6.86 seconds to first text;
initial model loading and prompt processing took 10.60 seconds in a fresh case.
Identical repeated prompts reuse more cache than a new conversation turn.

Whisper `base.en`, two CPU threads, took 1.93 and 1.58 seconds to transcribe a
4.54-second synthetic local TTS sample. This used the installed engine rather
than a mocked transcript. It did not use human microphone audio. The normal
1.5-second end-of-turn silence remains deliberate, and speech output waits for
complete sentences. Those times are separate from model processing.

At inspection, hands-free detection used about 24% of one CPU core; it dropped
near idle after disabling the microphone. Swap was in use on this 8 GB Mac.
These observations can contribute to variable timing, but the runner-switching
regression was independently reproduced and is a software issue.

## Verification and remaining limits

Regression tests reproduce the saved echo both during speaking and during the
follow-up window. Capture tests cover advertised/unsupported cancellation modes,
constraint errors, timeout, denied permission, Stop and late callbacks. Memory
tests retain exact suggestions, pending approval, personal-clause fallback and
consistent runtime capacity. Full check results and screenshots are retained
privately in the ignored `.june-work/voice-latency/` directory.

Final checks passed: **180 Python tests, 99 JavaScript tests, TypeScript and the
production build**. Review also verified that short trailing words such as
“why” and “no” are not discarded as noise, and that an echo-mode upgrade keeps
the track's noise suppression, gain, channel and other existing constraints.

In the updated browser, a fresh React answer completed, played through the
selected Nicky voice and was saved as complete. First text took 9.3 seconds,
10.0 seconds total, illustrating that a changed/cold prompt can still be slow
despite removing the repeated reload regression. Afterward the model remained
resident at 4096; the pure question did not trigger another inference.

The actual browser microphone reported **browser-managed echo cancellation**,
not system-audio cancellation. A live speaker-room test was requested; its
result must be recorded separately from the automated and synthetic checks.

Text matching cannot distinguish every speaker echo from a person repeating the
same words. System-audio cancellation depends on browser/device support and room
acoustics. A room-microphone test with speaker playback is required to establish
whether the remaining acoustic behaviour is acceptable; controlled transcripts
and synthetic fixtures do not prove that. Headphones avoid the speaker-to-mic
path when system-audio cancellation is unavailable or insufficient.

The small local model can still make factual mistakes. Older erroneous turns
remain visible as originally recorded, rather than being silently rewritten.
