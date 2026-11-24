# Next checkpoint: Naukri receipt reconciliation and batch clarity

Status: implemented and cross-reviewed by Codex and Claude, 22 November 2026. Automated and isolated real-UI checks pass; real-employer navigation acceptance remains pending. No new employer application was submitted during this work. Codex and the actual Claude main VS Code chat reviewed the recent interactions and source.

## Verified starting point

- Previous joint audit is deployed: backend 890/890, JS 373/373, typecheck/build pass. Isolated real UI passed card answer → next question → chat answer → completed fake application → applied status without reload. Production restoration/data checks passed.
- Fresh read-only health: June/Qwen3 4B ready; Mail, Screen and jobs enabled with no reported problem; no approved/running plan.
- New real sessions exposed a different boundary: several attempts returned a changed-page/unknown outcome; later visits to the same jobs found Applied and clicked nothing again. This supports a missing immediate confirmation path. The exact landing URL/timing and who completed each application are not established by those later reads.
- Ignitefortune Java job171126033465 was still not-confirmed. The planning pass used the existing read-only receipt check and Naukri now confirms Applied. No Apply, answer entry or Save was executed. The checker currently labels later receipts as finished by the user; that label itself does not establish authorship.
- Three later steps in the latest batch did not start after an uncertain step. The engine stopping is appropriate; the label Skipped does not explain why they never ran.
- A bare ordinal turn was stopped with no reply. That alone is not a routing bug; do not add a speculative fix.

## 1. Confirm the exact job after navigation

Owner: Codex backend (`jobs.py`, backend tests); Claude cross-review. Native changes only if evidence proves the existing read operations insufficient.

- Preserve the current write guards: no answer/Save on a changed question or different job, and no blind second Apply.
- After a dispatched Apply or final question entry leads off the reviewed job, use a shared bounded **read-only** reconciliation path: open the original reviewed job URL in a new June-owned tab, read its own Applied control, close only that probe tab.
- Check exact HTTPS host/job identity, current consent, stop and generation before and after awaits. The daily application limit must not block a read-only receipt check; account for confirmed applications idempotently without counting a receipt twice. Do not turn a revoked action into a success or an automatic retry. A different job, login, captcha, external-site page, timeout or missing Applied control remains honestly unconfirmed.
- Use at most three reads, normally at 0, 8 and 16 seconds within a 20-second total deadline, plus bounded probe-tab cleanup. Blank/loading tabs may settle; only the exact completed job page can confirm Applied. No model call or second click is needed.
- Record neutral receipt provenance: confirmed on the reviewed job page after navigation. Use neutral wording for the existing manual recheck as well; change no historical details. Preserve the original unknown step history. Do not infer that June or the user completed it merely from a later Applied label.
- Capture only minimal private diagnostic facts needed to explain navigation: scheme/host, scrubbed path shape, same-job boolean, stage and timing. Remove query values/fragments; never log page text, answers, tokens or a full potentially sensitive URL. Replace digit runs and identifiers in the path shape with placeholders. Keep logs size-capped in the private June data tools/diagnostics folder (0600 file, 0700 directory), using only allowlisted path prefixes.

## 2. Explain what happened to the rest of a batch

Owners: Claude `PlanCard`/panel/types/JS tests; Codex engine/route tests and any agreed additive progress metadata.

- Show confirmed, unconfirmed and not-started counts separately. Keep uncertainty visible even if earlier steps succeeded.
- An undispatched step blocked by an earlier unknown outcome reads **Not started — previous application not confirmed**, rather than suggesting the user skipped it. Add an explicit backend reason such as `blocked-by-unknown`, strictly parsed by the frontend; never infer this reason from `skipped` alone. User cancellation and other skip reasons remain distinct.
- Keep the existing stop-on-unknown engine behavior. Do not silently continue later jobs or resend the uncertain one.
- “Apply to the rest” prepares a review card for the explicitly identified, still-unstarted jobs from that conversation's batch. It does not execute by itself. Exclude already-applied jobs; reconcile uncertain jobs before offering them again. Missing/ambiguous batch context asks for clarification rather than guessing or using another chat's list.
- Agree minimal backend/frontend contract before edits; preserve existing review fingerprints and historical card text.

## 3. Prove the fixes

- Reproduce the recent failure with synthetic browser fixtures before fixing it.
- Cover redirect to a non-job page followed by exact-job Applied; no Applied after budget; unrelated job showing Applied; navigation after final Save; consent/stop during probe; closed tab; delay and timeout. Assert exactly one original Apply and zero reconciliation clicks/entries.
- Cover a batch with earlier success, one unknown step and later undispatched steps; verify counts, reasons and a context-bound review of only the rest. Include duplicate requests and already-applied exclusion.
- Extend the existing isolated real-UI harness with navigation/reconciliation and not-started batch states. Use the real frontend with temporary data and fake browser; preserve production data/model/grants and automatic restoration. Verify card/panel update without reload.
- Run relevant focused regressions, then typecheck/JS/backend/build against frozen final inputs, plus the native mock if applicable. One owner controls installation/restart; rebuild no unchanged helpers.
- A real-site acceptance run uses a separately identified authorised application and portal receipt. This planning pass authorises no new employer action. An isolated pass is not a real portal submission.

## Later, after this checkpoint

Next implementation slice is **8.7 simulated Home**, then **8.8 simulated transactions**, subject to scope approval. Home starts with clearly labelled virtual lights/switches, deterministic local state and no hardware/account connection. Transactions start with simulated cart/booking review, changed-total invalidation and duplicate prevention, with no real payment fields or charge. Neither is part of this receipt-fix plan.

Qwen 4B, context 4096, Heart voice, private facts, existing permissions and the dirty shared working tree stay preserved. Claude owns UI/design, Codex backend/runtime; coordinate before crossing file ownership. No automatic commits.

## Release evidence

- Full final frozen checks: typecheck exit 0; JS 376/376; backend 901/901; production build exit 0; diff-check clean. Eleven new backend receipt/continuation regressions cover navigation, final recruiter Save, wrong-job receipts, consent/stop/generation, timeout/closed tabs, loading blank tabs, daily limits, diagnostics, context/duplicate continuation requests and active-plan refusal.
- Claude's isolated production-UI scenario passed: first synthetic job reconciled Applied with one receipt read; second remained unconfirmed after three reads; third never started and showed the explicit reason. Exactly two original Apply clicks, zero real browser actions, panel/card counts updated with zero reloads. Evidence is private in `.june-work/isolated-ui-{result,driver,restoration}.json`.
- June production restored once: launcher 72922, supervisor 72932; ports 3001/8001 only, no 8002 listener. Snapshot hashes unchanged. Qwen 4B ready; Mail/Screen/jobs enabled with no reported problems; no active approved/running plans. Existing visible preview refreshed. No helpers changed or reinstalled.
- Remaining acceptance: observe the next specifically user-approved real employer application's navigation and exact portal receipt. Synthetic success does not establish live employer submission behavior. No such action was authorised by this implementation request.
