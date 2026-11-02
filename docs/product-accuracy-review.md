# Product-knowledge failure review — 2 November 2026

The saved conversation contained the correctly captured question `tell me about rtx 5080`, followed by a completed reply asserting that the card did not exist. After `it was released in 2025`, the model repeated the denial. This was an answer failure, not a changed model number in transcription. The selected runtime was Qwen3 4B Instruct.

NVIDIA's [30 January 2025 launch article](https://www.nvidia.com/en-au/geforce/news/rtx-5090-5080-out-now/) directly contradicts that answer. The earlier small acceptance set did not establish general factual accuracy; this additional real conversation is a failed example. Prior incorrect assistant statements also remained in the conversation context. A larger local model alone is not an adequate product-verification system.

## Bounded repair

The existing streamed graphics-card guard now intercepts unsupported categorical nonexistence/release denials for a named card and its immediate short clarification. It returns an honest lack-of-verification statement, rather than inventing replacement specifications or a launch date. Quote, fictional and supplied-source tasks bypass this new source check. Unrelated topics retain their normal streaming path. No product fact table, live search, training or automatic saved-memory change was introduced.

This guard is a limited prevention measure, not proof of accurate product knowledge or a general hallucination solution. Positive specification errors, unknown phrasings and unrelated factual errors can still pass. Reliable current product answers require sourced retrieval and evaluation of those sources. The model remains experimental and its earlier latency gate remains open.

## Verification

Six new checks cover both recorded wrong replies, a different vendor, split-stream delivery before voice, source/fiction task preservation and an unrelated topic change. The original examples failed before the guard change and passed afterward. The full Python suite passed 317 tests. The first full run exposed a separate cancellation-test isolation bug: it read the real saved model selection while its fake server only offered the environment default. Its data/configuration are now explicitly temporary; no runtime cancellation behavior was changed to make it pass.

The updated backend was restarted and `/api/status` reports Qwen3 4B Instruct ready. No fresh generated product answer or general accuracy pass is claimed by this verification; the exact observed generated failure was replayed through the real streaming adapter using controlled model frames. Existing chats and approved memories remain intact, including the visible earlier incorrect replies.
