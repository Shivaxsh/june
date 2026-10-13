# June basic answer reliability

Verified on 13 October 2026, Intel i5-8257U / 8 GB RAM / CPU-only Ollama.

## Evidence and selection

Only one candidate was downloaded: Qwen2.5 1.5B (about 986 MB). Existing Qwen3 0.6B remains installed. June stays local on port 3001, with unchanged speech interfaces, transcript review and roadmap progress. No public deployment is part of this repair.

The original Qwen3 model passed 6/8 checks with the existing prompt and temperature 0.1, but failed the country-with-I question twice. Qwen2.5 with that same prompt passed 7/8 but invented an unknown family detail. Therefore a model change alone was not sufficient.

A shorter prompt separates general knowledge from user-provided personal facts and clarifies user pronouns. The final candidate passed all eight original cases plus two personal-context cases (10/10) after actual answer inspection. An intermediate answer about the assistant's own food preferences was rejected despite a permissive text matcher; the prompt and evaluation were tightened before selection. Some unknown-personal replies remain awkwardly worded, but the final run did not invent those facts.

The application now defaults to Qwen2.5 1.5B, temperature 0.1, thinking disabled, context 4096 and reply cap 256. No country answer or other response is hardcoded. Existing conversation history is retained: injected refusal did not prevent a correct Tokyo answer on either model, so no history-stripping heuristic was added.

## Final observed model answers

| Check | Actual model answer | Total time |
|---|---|---|
| country-I | Indonesia. | 1.19s |
| capital | The capital of Japan is Tokyo. | 0.74s |
| arithmetic | 17 plus 28 is 45. | 1.02s |
| follow-up | Paris. | 0.51s |
| after-refusal | The capital of Japan is Tokyo. | 1.05s |
| other-letter | Zimbabwe. | 0.46s |
| unknown-personal | I do not have access to your personal information, including your mother's first name. | 1.56s |
| unknown-food | I do not have access to personal preferences or knowledge of what the user has shared. | 1.74s |
| known-personal | Your favourite colour is teal. | 0.9s |
| country-I-repeat | Indonesia. | 0.5s |

Ollama reported about 1.22 GB loaded footprint for the candidate versus 1.15 GB for the original, with no GPU allocation. These are runtime-reported footprints, not whole-system peak RAM. Initial loading/prompt processing was observed around 7–8 seconds during the first candidate trials; most subsequent short answers were under 3 seconds. The Mac already used about 3.4 GB swap, so keep one model loaded at a time and expect slower responses under load.

## Verification and limits

The reproducible model comparison is `scripts/evaluate-models.mjs`; it calls real Ollama and stores local evidence under ignored `.june-work`. Regression tests verify the selected installed default, conservative settings and preservation of follow-up messages. Existing speech/cancellation tests remain. Typed-streaming, spoken playback, Stop and New chat are checked against the restarted application; final results are appended below.

Ten synthetic prompts cannot establish broad factual reliability. This is an observed improvement for ordinary questions, not Claude-level reasoning. The model can still misunderstand questions, hallucinate or use outdated information. Current-information tasks need an actual retrieval/tool connection; later RAG will not automatically fix all reasoning errors.

Keep `.env.local`, runtime/models and raw local verification artifacts out of Git. Voice preferences and roadmap checkboxes were not modified.

## Final application checks

- All 41 regression tests passed, including real local speech-engine lifecycle tests. TypeScript and production build passed.
- Restarted app status reports qwen2.5:1.5b ready. Real /api/chat returned Indonesia in three streamed updates (~1.0s), and Tokyo after an injected refusal in seven updates (~2.9s).
- Browser typed question returned Indonesia (4.2s total / 3.7s first text). Hear reply used the existing selected Nicky female voice, with real playback/boundary captions. Stop voice worked.
- Stop cancelled a real photosynthesis generation and restored usable controls. The next follow-up used the preceding completed country answer, showing cancelled turns do not contaminate context.
- New chat cleared the verification conversation and restored idle. A subsequent fresh factual request returned Paris (6.4s total / 4.3s first text). Actual app latency can exceed direct-model timings.
- Existing user conversation was not cleared or reloaded; browser checks used a temporary tab. Voice/transcript interfaces and roadmap data were untouched. No paid provider or public deployment was added.
- Real microphone-to-reviewed-transcript behaviour was not re-certified with a new human utterance during this model repair. The previously working local capture/transcription implementation was preserved, and its regression suite passed. No Phase 3 completion checkbox was changed.

The screenshot is stored privately within the project at `.june-work/answer-reliability.png`. Changes are committed locally on codex/june-answer-reliability; the public Pages branch is unchanged.

Additional final checks: a live synthetic conversation containing three repeated refusals followed by a harmless country question returned Indonesia correctly. This more complex recovery case is included in the reusable evaluator. The fresh browser France conversation also answered the follow-up "Which country were we discussing?" with France (1.9s total). These checks use synthetic test history; no private user conversation was saved in the public source. Existing failed replies remain visible in their original conversation, but newly submitted requests use the updated model and prompt.
