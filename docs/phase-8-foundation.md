# Phase 8 implementation ledger

The user approved the full staged plan on 15 November 2026. Preserve Qwen 4B,
the local Heart voice, existing action approvals and Phase 7 behaviour. Use free
and local tools first; authorise online services separately. No automatic commits.

## Releases and acceptance

1. **8.0 Foundation:** bounded app-owned plans, exact reviewed payloads, safe
   remembered approvals, cancellation, receipts, outbound boundary and Keychain.
2. **8.1 Daily assistant:** on-request Google calendar/weather/local-goal briefing
   and a selected Apple Music playlist; scheduled open-page briefings later.
3. **8.2 Mac/MCP:** registered app actions, reviewed named Shortcuts, individually
   allowlisted tools; no model-generated shell.
4. **8.3 Documents:** editable template DOCX/PPTX plus rendered PDF inspection.
5. **8.4 Websites:** editable static source, desktop/mobile previews, exact reviewed
   GitHub Pages publication and rollback, isolated from existing dirty projects.
6. **8.5 Email/jobs:** Gmail reading, local drafts, exact reviewed sends; truthful
   portal applications and outcome tracking. Naukri first; unsupported submission
   routes require human handoff, never invented success.
7. **8.6 Screen:** opt-in single-request local OCR, no screenshot retention.
8. **8.7 Home:** simulated Home Assistant lights/switches; hardware and account
   setup are a separate, visibly pending live gate.
9. **8.8 Transactions:** simulated cart/booking review, changed-total invalidation,
   duplicate prevention, supported merchant adapters; human payment/authentication.

Each slice needs relevant regression tests, cross-review, full release checks,
actual output inspection and human acceptance when audible/interactive. Blocked
account or hardware setup never counts as a passed live gate.

## Ownership

Codex owns backend, native helpers, API bridges, scripts and backend tests. Claude
owns frontend/design/types and JS tests, including announced Chat.tsx changes.
Contracts agreed in chat before coding. Reviews are read-only across ownership.
One live-test/restart slot, no automatic microphone enable or real external writes.

## Foundation contract (version 1)

GET `/api/capabilities`, `/api/connections`, `/api/plans`; GET `/api/plans/{id}`.
POST `/api/plans` accepts only `{requestId,intent,input?}`; the initial executable
intent is `open-vscode`, with no input arguments. The application builds the steps.
Approve/cancel require `{requestId,revision,fingerprint}`; approve additionally
accepts `remember`. Revision identifies the immutable payload, not progress.
Errors have top-level `{code,message}`. Responses include `version:1` and
`serverNow` in milliseconds, plus a plan or bounded list.

Fingerprint covers ordered tool identities, exact stored payloads, previews,
permission policies, creation/expiry, identity and revision. The executor reads
the stored payload; it never reconstructs it from model text. Same request id and
body replays the plan; a conflicting operation/body returns 409. No effect retries.
Cancellation stops unstarted steps; an already dispatched effect may finish.
`cancelRequested:true` remains visible while that effect finishes.

Only exact approved local/read actions can be remembered. The VS Code adapter
shares existing Hands trust and native verification/audit. POST `/api/plans/forget`
with `{requestId}` clears remembered workflow approvals and the VS Code preference,
cancels approved undispatched plans, and prevents in-flight work restoring trust.

Restart/shutdown distinguishes undispatched cancellation, partial completion and
unknown dispatched outcomes. Never claim an unstarted tool ran. Tool results are
app-owned, bounded and independently verified by the adapter. Remote content must
never be returned as executable steps or a success receipt.

The outbound HTTP boundary requires enabled service consent, exact registered
HTTPS hosts, normal TLS verification, no redirects or environment proxy, finite
timeouts and bounded responses. It returns no provider error text. No external
connector is enabled in 8.0. The Keychain helper accepts fixed service/account
names and credentials only through stdin; it is compiled/self-tested without
reading or writing real credentials.

## Progress

- Source checkpoint verified: 331 tracked/untracked source files, copy-based,
  outside the repository; no index/worktree changes or credentials included.
- Backend regressions observed failing first: exact approval, request conflicts,
  cancellation, restart recovery, changed permissions, trust revocation during
  execution, private errors, real ASGI routes, outbound HTTP and credential pipes.
- Claude implemented the Integrations panel, strict parsers, bound review cards,
  cancellation, monotonic progress and forgetting approvals; focused tests passed.
- Claude cross-review B1/B2/B3 reproduced and fixed test-first: distinguish no
  dispatch from unknown outcome, and expose cancellation to other tabs.
- Foundation release checks passed: typecheck exit 0; JS 318/318; backend 575/575;
  production build exit 0; diff check exit 0. A later frontend layout regression
  requires the final combined rerun. Actual restarted endpoints returned HTTP 200
  with version 1. Claude mocked UI 375/1440 checks passed.
- Daily-assistant implementation and its setup/privacy/verification notes are in
  `docs/daily-assistant.md`. Final combined checks: typecheck0, JS331/331, backend598/598, build0, diff0. A real remembered VS Code workflow completed with native verification; default live briefing and temporary Good morning chat returned app-owned results. No real accounts or Music permission were enabled; human acceptance remains pending.

Ruling: preserve the shared dirty checkout and verified copy checkpoint instead
of creating a clean worktree or committing; the prior implementation is largely
untracked and shared with Claude. Cost: review must distinguish new foundation
files from existing uncommitted Phase 7 work.

Ruling: the foundation lists future connectors as unavailable and offers no fake
connect controls. Subsequent releases implement each adapter before enabling it.
