# June latency pass — 14 November 2026

User authorized planning with Claude and implementation. Existing edits and the current Qwen model, context and reply limits are preserved.

## Agreed work

- Codex: measure the model and backend stages on synthetic inputs; compare bounded optimizations; add validated timing telemetry and real inference-queue feedback.
- Claude: show measured waiting time and actual stages, fix prose after code-first replies, preserve document validation, interruption and continuation.
- Cross-review, focused regressions, combined checks, app restart and live typed-flow verification. Spoken Continue requires a person at the microphone; earlier wake/interruption acceptance remains valid.

## Measured baseline

CPU-only Qwen3 4B on this Intel Mac with 8 GB RAM. These are observations under the current workload, not guarantees. The OS reported a CPU speed limit of 58%; no OS settings were changed.

| Synthetic request | First text | Total | Model load | Prompt processing | Generation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Short explanation, model initially unloaded | 99.45 s | 173.31 s | 23.94 s | 74.95 s | 73.99 s |
| Identical short request, warm | 2.98 s | 24.82 s | 0.04 s | 2.28 s | 21.82 s |
| Calculator continuation, changed prompt | 21.54 s | 55.46 s | 0.01 s | 21.16 s | 33.93 s |
| Repeated calculator continuation, cached prompt | 0.72 s | 38.55 s | 0.01 s | 0.57 s | 37.82 s |

Raw model output and backend-visible text arrived together in these cases. The dominant measured costs were model loading, prompt processing and CPU generation.

## Experiments and decisions

- Removing the continuation-specific system hint: 59.19 s and 70.61 s total. Prompt work decreased slightly, but overall latency did not reliably improve. Rejected; instructions remain unchanged.
- Reducing processing batch to 64: 150.23 s after the required runner reload, then 56.63 s warm. Reload and hardware variation prevent a clean first-run comparison, and the warm result did not beat the existing baseline. Rejected; no batch override is shipped.
- Do not claim a generation speedup from these results. Preserve correctness and expose the real wait instead.

## Implemented and verification

Backend timing events report only validated numeric loading, prompt-processing, generation and first-new-text durations. The queue label is based on an occupied inference lock and clears when the slot is acquired. No private text or arbitrary model metadata enters telemetry.

Claude's frontend adds measured elapsed time after three seconds and uses only actual stages. Code-first replies can speak prose outside code fences. Raw JSON and transport-envelope replies must remain silent until validation; code is never read aloud.

`scripts/profile-latency.py --run` runs sequential synthetic comparisons without saved chats or voice. Reports are private files under `.june-work/latency-*`. Run using `backend/.venv/bin/python`; optional diagnostic variants never change defaults. Timing and Python syntax checks do not establish functional correctness of generated programs.

Final check and live verification results are recorded in `docs/handoff.md`.

## Final acceptance

All final checks passed: typecheck, 207 JavaScript tests, 464 backend tests and production build. June was restarted and left ready with its microphone off. Live code-first output plus explanation completed and saved in 30.3 s; native audio output was reported at 39.3 s. A second synthetic request visibly showed the measured 8-second waiting counter and completed in 42.2 s with the expected model-stage timings. No human listening or spoken-Continue acceptance is claimed. Both tuning candidates remain rejected; no reliable generation speedup was established.
