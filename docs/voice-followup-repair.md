# Spoken cut-offs, follow-up latency and recall

## Evidence and reproduced failures

The retained conversation contained complete written answers, followed by the
user reporting that the spoken sentence stopped early. The stored `allow`
fragment was reproducibly accepted as an interruption during the sentence
“The internet allows people to connect and share information across different
locations.” This is a playback-ownership problem, separate from model factual
errors. The original conversations were preserved.

Two more controller failures were reproduced before repair: an `idle` event
between queued sentences, and late callbacks from an ended utterance cancelling
or reviving a stream that was waiting for its next sentence. Passing synthetic
checks alone does not prove the room microphone problem has disappeared.

The name question “Can you do you remember what my name is?” incorrectly matched
the generic memory-capability route and bypassed recall retrieval. The database
had no approved facts; mentioning personal facts in yesterday's chat had created
pending proposals, not approval. The fourth fact in that message was outside the
three-suggestion limit. No personal fact was silently approved or ASR spelling
silently rewritten; the user expressly approved the corrected name and colour
in this repair session, and they were saved through June's existing UI.

## Changes

- A sentence ending reports waiting while another sentence is queued or the
  model stream remains open. Only an exhausted reply reports idle.
- Native speech callbacks and timers check both request token and utterance
  ownership; an already-ended utterance cannot affect the waiting stream.
- A clipped single-word prefix of known playback is not independent interruption
  evidence. Stop/wait commands, different identifiers and new questions retain
  their correction paths. This is conservative text evidence, not acoustic AEC.
- Disfluent personal recall bypasses the generic memory-explanation route.
  Approved facts and current user corrections remain available to the model;
  pending proposals never become approved recall implicitly.
- Simple, unambiguous approved name/colour lookups in a new recall context
  now return labelled saved data directly, without model paraphrasing or another
  inference. Any earlier non-recall user context (including corrections),
  ambiguous facts and other questions keep the model path. Only the exact
  memory used is reported. Recall questions also skip needless fact extraction.
- The Memory panel states approved and awaiting-review counts separately and
  explains correcting transcription errors before approval.
- Model context stays within the original 18-message / 4,000-character limits,
  but advances in four-turn blocks rather than dropping one turn on every
  request. Between advances, new turns append to an unchanged cached prefix.
  Complete source history is still retained. Typical short-turn long chats
  supply six to nine recent turns; large pairs can reduce the count further.
- Read the database context revision once per retrieval, not once per saved turn.
- Retain the selected model for 15 idle minutes instead of five, consistently
  for chat and extraction, reducing reloads while June is in use. The model
  still occupies RAM while retained; genuine cold loads remain separate.
- Present the same selected memory set in a stable order, so a different
  relevance ordering alone does not invalidate model history caching.
- Background ambiguous-fact extraction waits out the hands-free follow-up
  window. Exact pending proposals still save immediately without inference.
- Browser debug events report native speech start/end/cancel ownership, timing,
  queue counts and final boundary positions. No speech text, transcripts, audio
  or personal facts are written into these diagnostics. Wake/interruption events
  report turn ownership so a later recurrence can be traced rather than guessed.

## Measured local model timing

Sequential CPU-only `qwen2.5:1.5b` requests used a read-only copy of retained
history in memory and synthetic technical follow-ups. They did not write test
turns into the user's saved conversation. Both cases used the real model,
4096-token runtime capacity, the same character profile, short output and no
concurrent build/test workload. Every step asked a different question and
appended its actual answer; these were not identical-prompt repeats.

| Changed follow-up | Old sliding window: first text | Block window: first text |
| --- | ---: | ---: |
| CSS grid | 6.24 s | 0.59 s |
| JavaScript promise | 6.86 s | 0.40 s |
| Web worker | 7.37 s | 0.55 s |

Initial prompts were already partly cached and are excluded from this comparison.
Raw stage metrics and private diagnostics are under ignored
`.june-work/voice-latency/`. These are controlled samples, not guaranteed room
conversation timings. Model cold loads, changed profile/facts, window advances,
Whisper decoding and the selected 1.5-second silence interval remain separate
latency costs. The context policy intentionally trades some recent inference
history for steadier reuse; older source chats stay viewable and approved facts
remain separate. No model, voice, microphone pause setting or hardware changed.

## Verification

JavaScript: 103 passing checks. Python: 194 passing checks. TypeScript and the
production build succeeded. Focused regressions cover the saved cut-off fragment,
queued speech, late native callbacks, cancellation, disfluent recall, pending
versus approved facts, context bounds and stable memory prompt ordering.

After a full app/backend restart, the actual browser answered the original
name question correctly from approved facts: first text 1.8 s, total 2.5 s.
The selected Nicky voice emitted start and end events, reaching boundary 33 of
33 characters with no cancellation. A separate new chat initially recalled black through Qwen in 1.0 s total
(0.5 s first text); its native boundary reached 27 of 27 characters. Its wrong
first-person pronoun motivated the deterministic saved-fact lookup. The final
browser lookup returned “Saved memory: Your favorite color is black.” in 0.1 s
and reported only the single memory used. Further playback/room checks are
recorded below as performed, not assumed from tests.

## Limits

Text matching cannot reliably distinguish every speaker echo from a person
repeating the same words. Browser-managed echo cancellation does not establish
system-audio cancellation. A human speaker/fan test remains necessary before
claiming the original acoustic symptom is resolved. Whisper transcription is
unchanged in this patch; model-cache savings do not mean microphone recognition
itself became faster. The small model can still give wrong general-knowledge
answers; this patch does not train it or add live sources.

## Additional browser checks

The genuine two-sentence Internet answer reached native final boundaries
116/116 and 104/104. The next sentence started 67 ms after the first ended,
with no native cancellation event. This was speaker playback with hands-free
off, not proof of echo removal. The model had been unloaded at that point:
first text took 9.7 s and total generation 12.6 s, motivating the longer idle
retention. A 390-pixel mobile viewport had matching content and viewport widths
(no horizontal overflow); the memory controls and both approved facts remained
accessible. Temporary viewport overrides were reset.

Final live API checks through port 3001 used two real, nonpersisted Qwen turns:
a cold request took 15.33 s to first text / 16.74 s total; its changed follow-up
took 0.294 s to first text / 1.10 s total. Ollama then reported 899.99 seconds of
remaining residency at context length 4096, confirming the 15-minute setting
was applied. These are model/HTTP timings, excluding microphone capture, silence
detection, Whisper and speech synthesis. No background benchmark or build ran
during these calls.

Hands-free initialisation reached waiting-for-wake with the actual microphone
and browser-managed echo cancellation. No new human utterance arrived during
the requested room check, so the microphone was disabled afterward. Full
speaker/fan conversation verification is still pending; Phase 5/6 completion
and roadmap progress were not changed by this debugging work. Browser logs
showed no warning/error in the inspected flow. Existing voice settings and the
two unapproved suggestions were retained. Screenshots and full check logs stay
private under `.june-work/voice-latency/`.
