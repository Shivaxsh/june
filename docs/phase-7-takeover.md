# Phase 7 takeover — Claude owns all remaining work

15 November 2026. The user explicitly requested: hand everything remaining to Claude. Codex is stopping implementation and verification after delivering this handoff. All prior backend/frontend ownership boundaries are released to Claude. Preserve every existing uncommitted edit; no commits. Qwen 4B, original hints/batch512, saved local Heart voice and durable user data remain unchanged.

## Current code and findings

- Codex fixed `backend/june/library_chat.py` source selection for exact filename exclusions, sentence corrections, “rather than/without”, imperative “don't use/read”, additive “not only”, content negation and filenames with punctuation/control words. Bare exclusion and “the other one” ask when ambiguous. Forty additional synthetic selector variants passed.
- Added source-content discovery (“Which document mentions…”), app-owned inventory counts and short source-bound field follow-ups. Discovery was narrowed again after your cross-review: passport-document, backup-file and notes-app advice stays general.
- Real R24 exposed serialized citation metadata inside `documentAnswer` with valid citations. `knowledge_chat.validate_answer` now rejects leading JSON/backtick/tilde fences before persistence/playback; both structured model prompts request plain factual prose. `compose_reply` also rejects model-envelope fields inside serialized `generalAnswer` while allowing ordinary JSON/code samples.
- Your frontend fixes are present: refresh/status separation, queued follow-up refresh, unmount guard, deleted citation label, URL-encoded retry/cancel IDs, and prefixed document/mixed general metadata validation.
- Regression additions: `backend/tests/test_library_chat.py`, `backend/tests/test_knowledge.py`, new `backend/tests/test_routing_judge.py`; judge in `scripts/check-routing.py` now checks expected exact citation filenames; routing fixture set expanded from R01–R48 to R01–R60.

## One deliberately RED test to finish first

`test_library_chat.LibraryChatTests.test_inventory_outage_does_not_ask_model_to_invent_file_counts` was just added and reproduced a remaining bug. With `library=False`, “How many files do I have?” still reaches the general model. Log `.june-work/phase7-count-outage-red.log` contains the expected `AssertionError: No model for unavailable inventory`. NO production fix applied yet.

Suggested small fix: let `inventory_reply(question, documents)` accept `None`; recognize inventory/count questions before accessing documents and return `LIBRARY_UNAVAILABLE` for a recognized request when the service is absent. In automatic_chat call it even when `knowledge` is missing (currently gated by `if knowledge else None`). Keep unrelated general questions unaffected. Add or retain an assertion that the answer tells the user the library is unavailable. Run with:

```sh
PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m unittest test_library_chat.LibraryChatTests.test_inventory_outage_does_not_ask_model_to_invent_file_counts -v
```

## Actual checks so far

- Fresh document-only real-model baseline: **20/20**, 15 supported / 5 unsupported. All answers reviewed against the synthetic facts, including current/archive conflicts and injection. `.june-work/knowledge-acceptance-1v0lzem8/report.json` and `.june-work/phase7-baseline.log`. Baseline was before the later protocol-guard changes; do not portray it as a full final-code regression run.
- Latest focused backend before the new outage test: **69/69** (knowledge, library, routing judge), `.june-work/phase7-focused-final.log`. Punctuation filename regression passed afterwards too.
- Your latest focused frontend: **53/53**, tsc 0, as recorded in your chat.
- Interim root full checks: typecheck 0, JS **303/303**; backend **536/537**, the single discovery false-positive test failed against an older imported module while code was being fixed. `.june-work/phase7-{typecheck,js,backend}.log`. Further edits followed; fresh final full checks are REQUIRED. Never report this backend run green.

## Running real-model job — transfer, do not duplicate

At handoff, process **56485** is still running:

```sh
PYTHONPATH=backend backend/.venv/bin/python scripts/check-routing.py --run --cases R12,R13,R24,R25,R30,R49,R50,R51,R52,R53,R54,R55,R56,R57,R58,R59,R60
```

- Log `.june-work/phase7-routing-live.log`; reports `.june-work/routing-ve_lmfux/{baseline,summary}.json`.
- Latest snapshot: **14/19 completed, 11 passed**, failures R24 (metadata-as-answer), R25 and R30 (180-second timeouts). Remaining R56–R60; R08/R09 were included automatically to establish the follow-up group.
- This process imported the earlier code BEFORE the protocol fix and some later edge-case refinements. Retain it as discovery evidence, then rerun failures on final code. Do not run a second inference job concurrently. If the process ends/disappears, inspect report status and partial rows before restarting anything.
- The root exec session is 54854, inaccessible from Claude; use process/log/report state instead. User authorized you to take over the job, including cancelling it if necessary. Do not kill Ollama.
- Mac has been slow; runtime logs show ~1.2 tokens/s on one observed turn and ~2 prompt tokens/s. Heavy suites overlapped earlier timeouts. For diagnostic reruns avoid competing full suites. Parameters/defaults were not changed. Model log `.june-work/codex-next-model.log`.

## Remaining sequence

1. Finish the inventory-outage red test; review final backend/client guards and freeze code.
2. Let the transferred adversarial job finish. Inspect every failed answer; rerun R24/R25/R30 and any later failures on final code, without competing heavy jobs. Fix real bugs rather than relaxing rubrics; classify timeouts honestly.
3. Run requested parameter comparison using isolated request overrides, e.g. `scripts/check-routing.py --run --screen --path json --cases R51` (default plus six one-factor profiles: output caps, context 2048/4096, temperature 0/.1/.3). No saved-default mutation. Inspect cases and actual modelCalls/options, not just summary. Parameter checks have NOT run yet.
4. Run `npm run typecheck`, `npm test`, `npm run backend:test`, `npm run build`, `git diff --check` sequentially on frozen code. Record exact results and failed names. Don't overlap these with inference.
5. Restart only June's supervisor once to load backend changes; current app supervisor was PID52594, but recheck before signalling. Keep Ollama/model settings alone. Existing user planning reminder and timers must not be modified.
6. Real typed document/citation check in visible June preview, preferably with a disposable synthetic Workshop Audit note. Verify citation text/location and follow-up source. Clean up only your test data.
7. User explicitly answered **Yes—guide me when ready** for human hands-free document question plus follow-up. Have them enable mic deliberately; never auto-enable it. Ask a document fact, then “And the budget?” (or equivalent), hear both complete replies and inspect citations. Only record human acceptance after confirmation. General hands-free and recurring reminders were already human-accepted; they don't replace this gate.
8. Update `docs/phase-7-rigorous-audit.md`, `docs/phase-7-verification.md` and `docs/handoff.md` with final evidence/limits. No learning checkboxes changed automatically. Do not promise unrestricted perfection or entailment from finite tests.
