# False-interruption repair — 20 October 2026

## Reproduced faults

VAD only estimates whether sound resembles speech. Previously, 240 ms of voiced detection during generation, or 180 ms after a playback pause/settling interval, could cancel a reply before any words were recognised. Echo could bypass checks between sentences. Short checks remembered only the current sentence, and a wake-detector match bypassed the playback check entirely. The UI also called an unconfirmed sound “your interruption.”

## Repair

- Both generation and playback use a cancellable candidate verified **while native voice keeps playing**. No VAD-only pause or cancellation command is emitted.
- Confirmation uses local Whisper, continued speech evidence for ordinary phrases, and local phrase comparison with bounded recent playback captions. Captions arriving during the check update its reference.
- Noise, empty recognition and matching echo leave playback running. The remaining legacy pause-status labels say **Checking microphone sound**, not that an interruption has been confirmed.
- Audio-time accounting prevents CPU delays from being treated as extra audio. Candidate audio is bounded at 30 seconds and kept while decoding; a continuing question keeps its beginning.
- Speech arriving while a noise prefix is being decoded is rechecked before releasing the owned capture. There are at most three checks per candidate, each with an eight-second timeout.
- Actual speaking/generating/completion feedback remains visible during verification. Cancellation/stale ownership cannot resume a different turn. Verified wake-only interjections open a question window.
- Follow-up echo is excluded without excluding unrelated one-word replies such as “Linux.” A substantial, verbatim playback prefix is trimmed from overlapping microphone transcripts while preserving the user’s remaining text. Stop/New chat/disconnect still cancel owned jobs.

This changes application audio/turn handling. It does not train Qwen or establish the correctness of its factual answers. Recognition remains fallible, especially with native speaker output, airflow, overlapping voices or similar wording. Local word verification adds latency and CPU work; a genuine interruption may take a moment to stop playback. Headphones and keeping the microphone away from airflow reduce that risk. Manual transcript review remains available.

## Verification

Evidence is in ignored `.june-work/false-interruption/`; user recordings are not retained.

- New false-interruption regressions were observed failing before fixes. They cover sustained VAD noise, current/previous/late caption echo, generation gaps, wake false positives, follow-up echo, one-word follow-ups, decoder-tail retention, decoder hallucination without post-pause speech, pause/completion ownership and genuine barge-in.
- Final automated verification: **79 JavaScript tests + 124 Python tests (203 total)**, TypeScript check and production build passed. One pre-existing cancellation test depended on the child fixture writing a PID file within one second. Two reproduced failures were repaired by observing actual process creation and always cancelling/awaiting the owned job. A JavaScript cleanup test also observed unrelated production Whisper folders; its temporary directory is now isolated.
- Actual Silero/Vosk/Whisper synthetic checks: fan-like noise at RMS 0.005, 0.025 and 0.1 produced no probes or turns (peak VAD 0.019, 0.056 and 0.137). Final Nicky speaker-echo fixtures, including lingering output, produced **zero pause commands, zero interruptions and zero transcripts**; the voice kept playing. A different synthetic spoken question produced one interruption and one transcript.
- Initial production WebSocket check (before the quiet-verification revision): actual Vosk wake → Whisper transcript (1,627 ms); simulated playback pause/echo resumed; ordinary synthetic speech without a wake phrase interrupted once and preserved 5060 (final Whisper 1,274 ms); a real local Qwen request preserved the number (8.46 s total). Playback acknowledgements were simulated in this socket check; it is not a human-microphone echo test.
- Browser: selected Nicky voice started with captions and the speaking state; Stop voice returned to idle. Updated page loaded without console warnings/errors. The first human microphone check exposed repeated audible pauses and an echoed “Eating the page” fragment sent as a question. That failed check drove the quiet-verification revision and a fuzzy clipped-echo regression; it is not counted as a pass. After the revision, the user explicitly confirmed that microphone input and interruption work. Browser traces showed real “wait” and a changed-topic question getting through. They also exposed an overlapping playback prefix, now covered by a transcript-trimming regression.

### Diagnostic caveat

The first offline multi-scenario detector harness exited with a native Vosk segmentation fault. Subsequent detector runs and production WebSocket sessions completed, but its cause was not established. This is recorded rather than counted as a passing run. The application’s Python/runtime pins were not changed speculatively. If the backend exits again, retain the macOS crash report and reproduce that native-engine issue separately.

The first human check failed; the user subsequently confirmed microphone/interruption work after the quiet-verification change. Synthetic noise remains distinct from that human report. The final prefix-trimming change has deterministic regression coverage; a separate new human recording of that final trim was not requested. No new roadmap checkboxes or saved personality/voice preferences were changed.


## Repeating the wrong topic after a correction

A second user-reported fault was reproduced using the exact retained context and profile, read without modifying the private database. “I meant to react JavaScript, React.js” caused Qwen to apologise and repeat its previous web-worker paragraph. In a fresh chat it knew React.js; the failure was contextual anchoring, separate from microphone detection.

Correction turns now append a current-request focus instruction **after** personality/memory data. The latest user text is quoted JSON data; original roles/history and fixed capability boundaries remain intact. Ordinary follow-ups and explicit requests to repeat keep the original prompt/context behaviour. There is no hardcoded React.js answer, no context deletion and no model fine-tuning.

- The exact previously failing local context now returned a React.js explanation (5.1 seconds in one observed run).
- Reopening the original saved browser conversation and asking “I meant React.js. What is React.js? Keep it brief.” returned: “React.js is a JavaScript library for building user interfaces. It allows developers to create reusable components and manage complex UIs efficiently.” The written/spoken browser flow completed in 5.9 seconds; first text was observed at 4.2 seconds.
- Additional real local requests switched from React to CSS Grid, switched JavaScript to Python, and honoured an explicit request to repeat the greeting. These are narrow observed checks, not proof of general factual accuracy or perfect correction handling.
- Desktop 1280px and mobile 390px layouts had no horizontal document overflow; browser console warnings/errors were absent. Nicky remained selected and the microphone was off after verification. Screenshots are in ignored `.june-work/false-interruption/`.

Qwen remains fallible. The focused prompt improved these reproduced cases but cannot guarantee correct answers to every question; response timing varies with load on the Intel Mac.
