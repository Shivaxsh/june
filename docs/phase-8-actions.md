# June’s first Mac action

June can propose opening Visual Studio Code. Qwen 4B and its settings are unchanged. This is one Phase 8 capability, not completion of the broader integrations roadmap.

## Use it

Say or type **Open VS Code**, or open **Systems → Hands** and choose **Ask June to open VS Code**. June shows a review card with the exact effect. Choose **Approve** to run it or **Cancel** to leave the Mac alone. A proposal expires after five minutes. Saying or typing approval never executes an action.

Later refinement: the card can remember this one approval (see `docs/local-timers.md`). Once remembered, **Open VS Code** in Hands or chat runs the same fixed action without a new card, until the remembered approval is switched off in Hands. No other action can be remembered.

June reports the observed application state: active, running, failed, or unverified. A running app may be behind another window. An unverified outcome is not automatically retried. Ask **Did you open VS Code?** for the recorded result from this conversation.

The same card reopens with a saved conversation and shows its current outcome. Deleting that conversation removes its action links and cancels its unapproved proposals. Approved actions that have begun cannot be undone by deleting a chat.

## Scope and execution

Only `open-vscode`, with no arguments, is accepted. The server does not accept a shell, command, file path, URL, working directory, or model-generated program. Literal single-action requests can propose; quotes, negation, how-to questions and compound requests do not propose a partial action.

A fingerprint binds the server-generated id, fixed effect and deadline. Approval transitions from proposed to executing in a committed SQLite transaction before execution starts. Concurrent or repeated confirmations return the stored state. A dropped client connection leaves one bounded, tracked task to finish recording the result. A backend restart marks interrupted executions unverified and never repeats them.

`native/JuneActions.swift` uses the fixed `com.microsoft.VSCode` bundle with macOS NSWorkspace and separately checks the running application state. Its completion and timeout are serialized on the main queue. It does not request microphone, screen, account or accessibility access. `scripts/actions.mjs` compiles this private helper using the installed Apple SDK; building it does not open an app.

## Storage and API

Action records and their audit are in `actions/actions.sqlite3` beneath June’s private data directory. The directory is mode 0700 and the database mode 0600. Records contain fixed action metadata, ids, statuses and timestamps; no chat text or credentials. Records older than 30 days are pruned on action-service access. Chat associations are removed on chat deletion. Action history is not imported as authority to execute anything.

The same-origin Next bridge and loopback backend enforce local Host/Origin checks. Propose and decision bodies are capped at 1 KiB. Responses include a server clock for expiry display.

- `GET /api/actions`: availability and recent records.
- `POST /api/actions/propose`: exactly `{ "action": "open-vscode" }`.
- `POST /api/actions/{id}/approve`: `{ "fingerprint": "..." }`, optionally with `"remember": true|false` (saved only on a genuine proposed → executing approval).
- `POST /api/actions/{id}/cancel`: the same bound fingerprint.
- `POST /api/actions/preferences`: exactly `{ "openVSCodeWithoutApproval": true|false }`. `false` always forgets; `true` requires an earlier completed approved VS Code action. The UI only sends `false`.
- `POST /api/actions/run`: exactly `{ "action": "open-vscode", "requestId": "..." }`. Requires remembered approval; a repeated request id returns the stored outcome without a second launch.

A proposed card is a request for approval, not proof of execution. Other apps, files, accounts, devices and payments remain outside this action capability. See `docs/handoff.md` for checks actually run and live acceptance results.

## Verified scope

Final checks passed: typecheck, 217 JavaScript tests, 476 backend tests and production build. The native helper compiled. Live June showed a bound proposal, recorded one approved execution and observed VS Code active. VS Code was already open, so this proves activation of an existing app, not a cold launch. A separate live proposal was cancelled without a second execution. Do not close the shared development workspace to manufacture a cold-launch test. Spoken action proposals and cold launch remain untested; this does not mark the broader Phase 8 roadmap complete.

## Existing-app status refinement

Hands now shows an observed active/running/not-running/unknown snapshot, its age and Refresh status. It explicitly states that this is not continuous monitoring. Proposal text says opening or bringing an existing app forward; old proposals preserve their original bound review text. Approval-in-progress feedback prevents duplicate clicks. The final refinement passed typecheck, 222 JavaScript tests, 478 backend tests, production build and native compilation. Live status refresh and saved-card reopen passed without another execution. Qwen 4B remains unchanged.
## Saved project folders (2026-11-15)

The original app-only approval above remains scoped to VS Code without a folder. A separate saved-project capability now opens user-registered folders, each with its own approval. See [project-actions.md](project-actions.md) for registry controls, request shapes and result limits. This addition does not complete every item in the broader Phase 8 learning roadmap.
