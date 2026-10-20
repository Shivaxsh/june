# June v0.5 · Phase 6 verification

Verified on 20 October 2026 on the Intel i5-8257U MacBook Pro, 8 GB RAM. Baseline model: `qwen2.5:1.5b`, local Ollama 0.40.2; Whisper base.en; browser voice Nicky, American English. A proposed model comparison is separate from this release’s accepted baseline.

## Automated checks

- JavaScript: **79 passed**, zero failures, including the existing voice/interruption/renderer regressions and expression-rate checks.
- Python: **96 passed**, including real temporary SQLite migrations, permissions, 30-day boundary expiry, restart recovery, approved facts, rejection suppression, duplicate writes, source history retention, inference revision reset, atomic imports, failure states and low-priority cancellation.
- TypeScript: `npm run typecheck` passed.
- Production: `npm run build` passed; `/learn/phase-6` and the same-origin library route are present. The final running build was checked against current web-source modification times; no source is newer than the build.
- `git diff --check` passed. Python tests now isolate every FastAPI TestClient in a temporary data directory, so tests cannot change the private user database.
- The existing Starlette warning about httpx/httpx2 remains a dependency deprecation notice; it is not a failed test. No runtime dependency was changed to silence it.

## Real Qwen and persistence

An isolated private SQLite database exercised nine actual streamed local-model replies, not simulated responses:

1. User fixture stated “My project is Lantern.” Local extraction proposed that exact clause with an exact quotation. It was absent from approved memory until explicit approval.
2. A fresh conversation recalled Lantern. Reopening the database recalled it again.
3. A current correction to Beacon took priority over the saved Lantern fact.
4. Editing the saved fact reset historical inference context; the next real reply said Beacon, without Lantern.
5. Deleting it left source history visible, but the next real reply said it did not know the project name. Neither old project name reappeared.
6. Steady/calm/bright were evaluated on the same short explanation prompt. Answers varied; style configuration does not guarantee factual correctness or perfectly short replies.

Observed isolated reply totals: roughly **1.4–21.8 seconds**, depending on prompt and cache state. Extraction took **11.8 seconds** in the recorded run. Browser checks varied from **2.9–25.1 seconds**, including model contention/cold context; these are observations, not a performance guarantee.

## Browser acceptance

- Enter sent once; the genuine local answer streamed, was labelled complete and was confirmed saved.
- Memory showed a model-generated Cedar fact and exact quote; approval saved it. New chat preserved the earlier chat and recalled Cedar with one memory ID exposed beneath the answer.
- After a full backend/model restart, another fresh browser conversation recalled Cedar again.
- Search found the earlier source chat; reopening restored its written messages.
- A second June tab edited the fact. The first tab received context invalidation while retaining visible source history. Deleting its active source chat through the same API used by other clients, followed by a cross-tab refresh, cleared the stale conversation ID. The first tab then sent a fresh message and received a real model reply successfully.
- Nicky remained selected across restart. Automatic playback/replay, captions, honest speech approximation and Stop voice were observed. New chat/visibility and cross-tab invalidation released active work; existing natural-interruption tests stayed green.
- All ten workshop fields rendered. Workshop JSON import showed a preview, changed nothing until Save, and ignored the fixture’s roadmap-progress flag. Calm expression saved and reloaded; Still view stayed static.
- Browser export downloaded valid June JSON with chats excluded by default. Import validation, conflicts/rollback and pending-export recovery are covered by regressions.
- Desktop 1280 × 900 and mobile 390 × 844 checked. Chat/personality and Phase 6 studio had no horizontal overflow; keyboard Enter changed learning topics; Still view and renderer reduced-motion cleanup regressions passed. The Phase 6 studio presents all seven topics in workbook order.
- No warnings/errors were captured in the final verification tab. Charcoal colours, transparent network face, selected voice and existing speech/status routes are retained.
- SQLite permissions checked: directory `0700`, database `0600`.
- All synthetic chat/memory fixtures were removed from the private live database; the approved warm, concise, practical default profile was restored. Existing user progress and personality workshop answers were not overwritten.

## Review repairs

Fresh review identified and reproduced four defects before delivery: explicit temporary mode still reading a damaged database, another tab retaining a deleted active chat ID, PIN credential filtering, and exported pending turns failing re-import. Each was repaired and checked. An additional regression fixed offline model preflight discarding failed turn history. Further checks reject malformed Unicode/profile data, protect repeated approvals and stale completions, bound complete profile fields, and export chats beyond the recent-list limit.

## Limits

No new human microphone/room-echo conversation was performed for this memory release. Voice event/UI checks and existing automated voice regressions are distinct from human microphone verification; prior roadmap progress was preserved as found. Small-model factual mistakes and inconsistent phrasing remain possible. Suggestions intentionally require exact user clauses and may miss useful facts. Fixed prompts cannot guarantee resistance to every malicious instruction; saved facts are application data, never executable tools. No cloud service, model training or computer/account actions were added.

Private screenshots, fixture logs and raw exports are under ignored `.june-work/phase-6/`. The progress backup is stored separately under June’s private application-support backups folder. Public `main` and published v0.4 remain unchanged.
