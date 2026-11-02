# June reliability baseline — 2 November 2026

This closes the bounded application check with explicit remaining limits. It does not certify every model answer or mark the full room-acoustic gate complete. The user accepted documenting this Mac's constraints instead of repeatedly chasing the same speed target.

## Configuration preserved

Intel i5 MacBook Pro, 8 GB RAM; local Qwen3 4B Instruct selected for experimentation, Qwen2.5 1.5B available through Local model; Whisper base.en conservative four-thread decoder; Nicky native playback; port 3001. No paid service, download, automatic memory approval or hardware purchase was introduced. Saved chats, approved memories, personality, appearance and public GitHub versions are preserved.

## Observed timing, not a promise

A browser request asked: “In one short sentence, what does a web worker do?” All voice components and the selected model reported warm before submission, and the Python/JavaScript test workloads had finished. The model returned a complete, relevant explanation of background work without blocking the main interface.

| Stage | Observed |
|---|---:|
| Submit → first text | 3.1 seconds |
| Submit → full written reply | 7.6 seconds |
| Submit → first playback event | 8.16 seconds |
| Native first-segment preparation | 510 milliseconds |
| Submit → final playback end | 15.59 seconds |

This was typed input and event-based playback timing, not a microphone or independently measured acoustic test. End detection and transcription would add time. It is one short example, not a median/p95 dataset. The 4B model's earlier browser run took 96.1 seconds to first text; that separate cold/context-heavy observation must not be mixed into a warm sample.

The 8.16-second playback onset already exceeds the earlier six-second upper target without transcription. Do not ask for another full twenty-turn room test just to reconfirm this known performance miss. CPU inference, limited available memory and sentence accumulation contribute to the observed delay; these measurements do not isolate the proportion attributable to each. More powerful hardware may improve speed but cannot guarantee factual accuracy.

## Application repair

The voice-status endpoint could combine `state: preparing` and `modelWarm: false` with the stale message “Local voice components are warm.” Readiness now names the currently missing components instead of reusing the last successful preparation message. A failing regression reproduced the issue; controller and HTTP tests verify the corrected message, including expired model residency.

No recognition, interruption, context, speech queue or decoding policy was changed to conceal a failed target. The faster greedy decoder remains withheld. Existing unsupported product-release guard prevents the recorded categorical denial pattern, but is not a verified product database or universal hallucination solution.

## Remaining limits and next boundary

- Speed targets remain **not met/deferred on the present baseline**, not passed: warm median ≤3.5 seconds, p95 ≤6 seconds, interruption ≤0.5 seconds.
- Full physical speaker/headphone, fan-on/off acceptance and measured interruption latency remain unverified. Earlier user reports that listening worked are qualitative evidence, not twenty measured turns.
- General model accuracy remains limited; the RTX denial and smaller models' threading errors are recorded failures. Do not keep adding benchmark-specific canned answers. Sourced web/document retrieval is the next capability to plan separately.
- No roadmap completion checkbox was changed. Moving to another capability must not imply the earlier acoustic or speed gates passed.

## Verification and recovery

See the final run totals below. The recovery snapshot is stored privately under June's application-support backups directory and contains a SQLite backup with an integrity check, committed Git history and local configuration/model selection. Model weights and rebuildable helpers are not duplicated. Browser-only preferences remain in the existing browser profile; they are not claimed to be included in this snapshot.

Final verification: 319 Python tests passed in 26.415 seconds. The same bounded gate session also passed 132 JavaScript tests before this Python-only readiness repair. No frontend source or API shape changed afterward; TypeScript and production-build evidence remains the model-selector build documented in `model-selector.md`. `git diff --check` passed. No synthetic fixture is counted as a human room turn.
