# June voice interruption repair

## What was wrong

The old voice state manager deliberately ignored ordinary speech while June answered. Interruption depended on detecting “Hey June.” In the reported GPU exchange, at least one accepted transcript already said 5070 Ti correctly, while Qwen answered about 3070 Ti. An annotated cough was also sent as a question.

## What changed

- Natural speech can interrupt generation and playback after explicit hands-free activation. The wake phrase is still required to start an idle conversation.
- Playback briefly holds its sentence queue while the browser acknowledges pausing. Continuing speech confirms a new turn. A short interjection gets a bounded local transcription check against the current spoken sentence, so “wait” need not be repeated or stretched out.
- Echo references and transcripts use the same number normalization. Late pause acknowledgements, old transcription results and sentence-end callbacks cannot revive cancelled work.
- Interruption audio is sliced on complete PCM16 samples. This fixes a malformed-WAV failure reproduced through the real pipeline.
- Recognised noise annotations are removed. Consecutive spoken digit words such as “five zero six zero” become 5060; valid numbers are not guessed or remapped.
- A narrow GPU identity check buffers sentences before speech and catches obvious substitutions, including changes to suffixes such as Ti. It does not validate product facts, prices or every possible phrasing.
- June’s prompt prioritises corrections and admits that current product information cannot be verified locally.

## Evidence and limits

- 20 clean synthetic speech fixtures distinguished 5060, 3060, 4060 and an unrelated code using the existing base.en decoder. The decoder remains unchanged. Human speech accuracy is still variable.
- The actual local Vosk/Silero/Whisper pipeline accepted an interruption without a wake phrase and produced 5060. Whisper took 1.8 seconds; the subsequent local Qwen check retained that number and took 4.2 seconds. Playback control in this transport test was simulated.
- The first actual browser microphone test captured a synthetic spoken question and began a local reply. It exposed an asynchronous native-pause bug missed by mocks; acknowledgement handling was corrected and regression-tested.
- A cold browser/model run during other verification work took 36.6 seconds total, with first written text at 28.1 seconds. This is not a fast-response guarantee; the Intel Mac uses CPU inference and performance varies with load.
- The pause probe is a practical check, not full reference-audio acoustic echo cancellation. A noisy room, quiet interjections, recognition mistakes and speakers can still affect results. Headphones reduce room echo.
- No recordings, transcripts or conversations are persisted by the application. Test fixtures are synthetic and kept in the ignored local work folder.

A fresh browser retry, screenshots and final test totals are recorded in `phase-5-verification.md`. Phase 5 stays unchecked until a human microphone conversation includes a spoken reply, a follow-up and a natural interruption.
