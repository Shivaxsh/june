# In-app local model selection

Open **Local model** below June's connection bar. Select an installed model, then **Use this model**. The current choices on this Mac are Qwen2.5 1.5B and Qwen3 4B Instruct 2507 Q4_K_M. No download is performed.

The choice is saved privately outside Git alongside June's database, survives restarts and applies to all June tabs. Switch only while replies, capture and playback are stopped. Background extraction/warm-up is cancelled before switching, and the old model's residency is released. Chat and voice readiness use the new selection; an existing learning-page WebSocket reads it for each new request. Thinking-only models are rejected.

Conversations, approved facts, personality, voice preferences and public hosting are unchanged. A fresh chat gives a cleaner comparison than continuing the previous model's history. An installed model may still need a slow initial load.

## Verification — 2 November 2026

- 311 Python tests passed, including nine model-selection tests covering installed/missing/incompatible choices, restart persistence, same-origin validation, request bounds, failed saves, active voice/chat exclusion, warm-up cancellation and actual request routing.
- 132 JavaScript tests passed; TypeScript and the production build passed.
- Applied Qwen3 4B Instruct through the browser's new control, received a real complete two-sentence reply correctly denying that an async JavaScript function moves a heavy calculation onto another thread, and heard Nicky play it. The selector was disabled during generation/playback. Reload preserved the model choice and Nicky; the microphone remained off.
- This run took 96.1 seconds to first text, 118.6 seconds for full text and 113.87 seconds to first audio. This confirms functionality, not acceptable voice latency. The model remains explicitly experimental on the Intel/8 GB Mac; the earlier latency gate is still open.
- Screenshot retained privately at `.june-work/model-picker/selector.png`; the selector fits the browser's existing narrow viewport without clipping.
