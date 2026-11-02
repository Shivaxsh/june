# Model and audio comparison — 31 October 2026

## Accuracy gate correction

The short async follow-up judge previously accepted any answer containing a negative keyword. Qwen 3.5 2B exposed a false pass: it denied automatic data transfer but incorrectly described moving control flow between threads and copying data with an unrelated API. The acceptance judge now also requires a relevant threading explanation and rejects that reproduced confusion. A failing regression reproduced the false pass before the repair; both judge tests now pass. Manual review remains necessary: keyword checks are not complete semantic evaluation.

The harness also checks that the configured model is installed before cloning data or scoring answers. An interrupted download had otherwise produced meaningless failures from an unavailable model. That score is discarded. Installed/missing model preflight tests pass; no unavailable candidate is counted as evaluated.

## Prompt cache layout

Identifier-repetition requests placed the changing identifier instruction before the stable personality/memory section. That invalidated the reusable prefix for the text following it. The stable section now precedes the changing instruction, matching the ordinary warm-up prefix. A regression failed before the change and now passes, verifying one complete memory section and the stable prefix for different identifiers. This is a cache-layout repair, not a hardcoded answer, and still uses genuine inference. No latency reduction is claimed from code inspection alone.

After the change, two warm genuine Qwen2.5 requests produced the complete correct identifiers in **1,604 ms (5060)** and **1,212 ms (5070 Ti)**. Earlier acceptance observations were 5,209 ms and 9,242 ms respectively; these are separate runs, not a controlled paired acoustic benchmark. The new measurements exclude listening, transcription and spoken playback.

## Installed model comparison

Qwen 3.5 2B Q4_K_M was evaluated on a private SQLite clone with the existing acceptance sequence and thinking disabled. The original loose judge reported 28/28; reviewed scoring is **27/28**. It did not resolve the real short async failure. Its first-text observations included 9.48 seconds for the CPU/async question and 8.52 seconds for the Web Worker question; the first React request was 25.60 seconds and includes startup effects. These measurements do not establish acoustic latency. The candidate is rejected and is not selected as June's default.

[Qwen 3 1.7B](https://ollama.com/library/qwen3:1.7b) was downloaded from the official registry after one resumed transfer and evaluated with thinking disabled. It also scored **27/28**: its short async follow-up described moving tasks between threads and switched to C++. Its more explicit CPU-loop answer began correctly but then wrongly suggested that async lets the loop avoid blocking. These manual-review failures disqualify it despite the other passing checks. It is not selected as the default.

Two generic browser-context cues were also tested privately with Qwen2.5. Both still produced incorrect threading claims. Those cues are **not shipped**. No benchmark answer is inserted into the production prompt. Qwen2.5 1.5B remains selected; all three tested small models retain an observed accuracy blocker. A larger-model evaluation requires a speed/accuracy tradeoff; the reliability gate remains open.

## Conservative Whisper thread tuning

The same eight existing synthetic fixtures were decoded sequentially with two and four CPU threads, after model warm-up and without concurrent model inference, builds or tests. Both profiles use beam search five, best-of five and the established temperature fallback; the greedy candidate remains disabled.

| Profile | Median transcription | Transcript agreement |
|---|---:|---|
| Two threads | 1,764 ms | Baseline |
| Four threads | 1,382.5 ms | 8/8 identical to baseline |

Four threads reduced the sample median by about **21.6%** without changing any fixture transcript. The native worker now uses four threads and speech status exposes this as optional `threads` metadata. The installed worker was rebuilt and passed readiness. Native control-loop tests validate the thread setting, conservative parameters and cancellation; all **299 Python tests pass**.

This does not fix the proper-name misspellings shared by both profiles, and it is not a measured human room-latency improvement. No microphone recordings were created for this comparison. Saved memory, conversations, Nicky and the user interface are unchanged. The overall reliability gate remains open.
