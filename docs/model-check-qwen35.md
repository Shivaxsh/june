# Qwen 3.5 2B local check · 20 October 2026

## Recommendation

Qwen 3.5 2B Q4 **runs on this Mac**, but this check does not support replacing June’s current `qwen2.5:1.5b` for everyday voice use. Keep the candidate installed for further experiments. Qwen 3.5 4B was not downloaded or measured; it is a heavier candidate, and its practical latency on this Mac remains unknown.

Machine: Intel i5-8257U, 8 GB RAM, macOS 15.8.1. Runtime: Ollama 0.40.2, CPU only. The official [2B Q4 tag](https://ollama.com/library/qwen3.5:2b-q4_K_M) is approximately 1.9 GB on disk; the [4B Q4 tag](https://ollama.com/library/qwen3.5:4b-q4_K_M) is approximately 3.3 GB. Download size is not a guarantee of total runtime RAM. [Ollama’s macOS requirements](https://docs.ollama.com/macos) list Intel/x86 inference as CPU only.

## Same-settings comparison

The two models received the same June fixed prompt, default personality, deliberately supplied memory fixtures where applicable, and a small set of eleven checks. Requests went directly to local Ollama; no real user chats, saved facts or commercial AI services were involved. This evaluated raw model replies without June’s GPU-identifier output guard.

Settings: thinking disabled, context 4,096, output cap 128 tokens, temperature 0.1, one model loaded at a time. These mirror June’s key settings; the output cap was reduced to bound the experiment. Model-native defaults for other sampling parameters remain different. Token counters and first-text timing came from streamed Ollama events.

| Model | Checks passed | Median first text, excluding initial query |
|---|---:|---:|
| Qwen2.5 1.5B Q4_K_M | 10/11 | 0.46 seconds |
| Qwen3.5 2B Q4_K_M | 8/11 | 20.55 seconds |

This is a small application regression set, **not a general model ranking**. The models were not exhaustively evaluated or fine-tuned. The medians exclude cold loading but include each subsequent prompt’s processing; prefix caching differs between architectures. They are not end-to-end microphone-to-speech timings.

Checks covered a basic country fact, JavaScript CPU/threading, the async/await standardisation year, 5060 correction, exact 5070 Ti identity, saved-fact recall, current corrections, unknown personal facts, honest capability limits, a five-word constraint and arithmetic. Both missed the five-word constraint. Under June’s current prompt, the candidate also refused the country question unnecessarily and falsely claimed that Promise.all/async/await distributes CPU work across threads. Those are model-output failures, independent of the microphone pipeline.

Ollama reported about 6.29 GB allocated for the candidate at 4K context, versus about 1.22 GB for the baseline. This is **Ollama’s allocation estimate, not a measured peak resident-RAM figure**. The system used roughly 2.3–2.8 GB of swap during these checks; that includes other running apps and cannot all be attributed to the candidate.

## Smaller-context diagnostic

A separate, limited probe used context 2,048, batch 64, four threads, temperature 0.7, top-p 0.8 and top-k 20:

- A short system prompt answered “Ireland” correctly; first text took 9.68 seconds including reloading/reconfiguration.
- June’s full prompt took 30.11 seconds before a JavaScript answer. It mentioned workers but still inaccurately suggested async alone schedules CPU work for later execution.
- Approved-memory recall returned Lantern correctly, with first text in 2.8 seconds.
- Ollama’s reported allocation remained around 6.17 GB. These few varied runs do not establish a consistently fast configuration or isolate which individual parameter caused a change.

The actual Phase 6 extraction controller was also run in temporary SQLite stores. Neither of two ordinary personal-fact fixtures produced a valid suggestion (23.16 and 10.23 seconds). The fictional-scenario guard correctly returned no suggestion. No fact was automatically approved. This reinforces that a replacement model needs application-level evaluation, not just a successful load.

## State left behind

- June’s live configuration remains `qwen2.5:1.5b`.
- The 2B Q4 candidate is installed under June’s private model directory for future experiments; its digest begins `1e2d21a4f03a`.
- The candidate was unloaded after testing, and the baseline was loaded and checked again.
- June’s application code, approved-memory rules, voice identity, roadmap progress and public GitHub branches were not changed by the comparison.
- Reproducible request scripts and raw synthetic results are in ignored `.june-work/model-qwen35/`.

Future comparison work can test additional prompts/seeds and model-specific settings. A candidate should pass recall, extraction, correction, safe tool proposals and latency checks before becoming June’s default.
