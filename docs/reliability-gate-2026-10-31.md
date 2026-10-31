# Reliability gate — 31 October 2026

The next phase remains on hold until the acceptance gates pass. This report distinguishes model/service tests, browser checks and human room observations. No synthetic fixture counts as a human turn.

## Isolated acceptance

`PYTHONPATH=backend backend/.venv/bin/python scripts/check-reliability.py` opens the live database read-only and uses SQLite backup to create a private, ignored clone. Only that clone receives test conversations and memory edits/deletion. Reports may contain personal reply text; they remain private under `.june-work/` and must not be published.

Initial result: 25/27 passed. All fourteen turns persisted, but turns thirteen and fourteen repeated an older project code after the user corrected it. This was model anchoring on older assistant answers, not a duplicate submission or a database limit.

Repair: retain the newest explicit user correction/update as quoted context on its follow-ups, without dropping unrelated history, approving memory, or changing model weights. A regression reproduced the missing context before the repair. The real-Qwen rerun passed **27/27**:

- Approved name/colour after New chat and reopening SQLite.
- React explanation, async CPU/thread behaviour and Web Worker DOM limitations.
- Corrected 5060 and complete 5070 Ti identifiers; honest booking capability.
- Fourteen-turn conversation, including a newer project-code update and subsequent recall.
- Current personal correction taking priority; edited and deleted facts removed from obsolete inference context.

Final regressions after the live wake-boundary and interruption-recall repairs: **294 Python tests and 132 JavaScript tests pass**. TypeScript and the production build pass; the final two repairs are Python-only. Browser timing diagnostics contain stage durations, timestamps and ownership IDs only; no transcript or audio content is logged by those diagnostics. These are observation aids, not proof of physical acoustic latency.

The real-model acceptance script was then extended to include the actual short spoken async follow-up after a Web Worker discussion, and to use the actual `Wait` recall prefix. Its final result is **27/28**: the short async follow-up still fails. The prior 27/27 result applies to the narrower original set and is not a release pass. Unit regressions do not override this real-model failure.

## Human room gate

The user confirmed availability. The test card is [the twenty-turn room check](v0.5.1-room-check.md). Tests/builds were stopped and all local components were warm before the session. The microphone was off; enablement remains deliberate.

The first live batch failed before completion: the confirmed standalone wake phrase was transcribed as `Hey, Jude.` and was submitted as a user question. The following question could then lose its buffered beginning. The batch was stopped and native ownership released; the UI showed microphone off and idle. The user had not reported the hardware/fan condition, so none of the four conditions is counted as passed.

Repair: ASR wake homophones `Jun`/`Jude` are accepted only inside a question window already opened by confirmed lexical wake detection. They are not globally substituted in ordinary speech or personal names. The regression recreates a wake-only decode while the user question is buffered and requires exactly one final question. Unconfirmed names/questions remain unchanged. The failing regression passed after the repair.

One completed live turn had measured input-end detection 800 ms, transcription 1,768 ms and request-to-first-playback 2,946 ms: approximately **5.51 seconds** in combined stage estimates. This sample is above 3.5 seconds; there are not twenty samples to establish a median or p95. These lifecycle estimates are not independent acoustic-onset measurements.

Pending after that repair: the full speakers/headphones, fan-on/off matrix; zero false activations; complete playback; natural interruption latency; and twenty voice latency samples. Do not mark this gate passed from automated tests or availability alone.

### Earphone check after the wake-boundary repair

The user clarified that this session used earphones. The recorded second session contains five questions once. Fan state and earphone route/type were not confirmed. The user subsequently reported that earlier tests in other conditions listened properly too. That is retained as qualitative listening evidence; it is not a twenty-turn measured latency or acoustic-onset dataset.

- Standalone wake preserved the full Web Worker question, with no separate wake message.
- All five intended questions were captured; no additional self-generated input was visible in this five-turn session.
- Ordinary speech interrupted the long reply and captured the full subsequent question. Its partial/stopped label was expected. Physical interruption delay was not measured.
- `5060, not 3060` was repeated as `5060`.
- The async follow-up received an incorrect C# threading explanation. This is a model-answer failure.
- `Wait, what is my approved name?` bypassed recall and received an incorrect denial. A failing regression covered seven interruption/discourse prefixes; request normalization now preserves direct approved recall for them. This changes routing, not the saved facts or model weights.

Detected-end-to-playback estimates for the five turns were **5.637, 9.385, 5.261, 6.377 and 8.167 seconds**: sample median **6.377 seconds**, sample nearest-rank p95 **9.385 seconds**. Both exceed the requested targets. They are five callback-based estimates, not a twenty-turn acoustic benchmark. The last sample used the faulty recall route before its repair.

The microphone was disabled and the next phase remains **blocked**. No further human repetitions were requested after the earphone clarification. Repeating tests without improving the failing model/latency paths would not establish readiness.

After deploying the recall-prefix repair, the exact `Wait, what is my approved name?` request returned the correct approved name through the running browser interface, with its saved-memory source label and Nicky playback. First text was about 0.1 seconds for this application-owned recall. This does not describe full voice-input latency. Microphone capture remained off.

Speed targets remain median ≤3.5 seconds and nearest-rank p95 ≤6 seconds from finishing speech to first audible output, and interruption ≤0.5 seconds. Client event estimates and human observations must be reported separately. Cold startup is separate. The faster decoder remains withheld because its exact-name gate did not pass.

## Recovery and completion

A private recovery snapshot contains a verified SQLite backup, Git bundle, ignored local configuration and recovery instructions under June's application-support backup directory. Its integrity check passed. Models and helper binaries are rebuildable and are not copied into Git.

No live approved fact was edited/deleted by the isolated tests. No roadmap completion checkbox or published GitHub version was changed. General model answers still require scrutiny: these fixed tests do not establish perfect factual knowledge, current product recommendations or universal instruction following.

The truncated live `web worker` input received an incorrect server-side explanation, despite the complete isolated Web Worker question passing. Normal-use messages visible before the test also included an unsupported current GPU recommendation and an unnecessary refusal of PC-planning advice. These are recorded model-reliability failures, not solved by microphone repair or claimed permanent training. A clean real-voice explanation still needs verification; the next phase remains on hold.
