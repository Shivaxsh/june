# Conversation reliability audit — 21 October 2026

## Scope and evidence

Reviewed the three retained conversations and replayed selected failures with
their saved context and personality settings. The original 28 turns were not
rewritten or deleted. Test examples use fictional names in isolated databases.
This work changes application logic and inference context, not model weights.

## Repairs

| Failure | Repair |
| --- | --- |
| June claimed to be made by Anthropic and denied having application memory. | Direct questions about June's identity, memory and unavailable purchase/booking tools receive explicitly labelled **June app information** from application configuration. Ordinary knowledge and personal recall still use Qwen. These are not simulated model replies. |
| A confirmation after a correct geography answer produced an unrelated refusal. Replaying a false assistant answer made Qwen agree with it. | Bare confirmation questions re-answer the original substantive question without feeding its unverified assistant answer back as a model example. Consecutive confirmations resolve to the same question. Saved messages remain unchanged. This is a fresh model answer, not independent fact verification. |
| A GDP ranking was invented without a year, metric or source. | The reproduced ranking request explains the missing dated source, asks for needed metric/year, and retains the source requirement after a short clarification. June still has no browsing or live ranking tool. |
| Clear user facts never reached the approval queue before the next voice turn cancelled extraction. | Up to three clear first-person clauses become pending suggestions atomically with a successful real-mode turn. Exact words are retained. Other prose still uses validated, cancellable model extraction. Neither path approves memory. |
| Old successful turns had no suggestions. | Explicit extraction is idempotent and can recover these suggestions without a model job. Three pending proposals were recovered from one existing turn, after a private database backup. Approved memory count stayed zero; the original turn contents were checked unchanged. |
| Opt-outs, attributed examples and abbreviations were mishandled. | Both extraction paths use a shared conservative exclusion guard. Exact clauses preserve names such as `Dr. Mira Sen` and `St. Louis`; explicit opt-outs and attributed quotations do not become proposals. |
| A GPU list triggered a single-card substitution warning. | Connected lists allow all named identifiers, including articles and suffixes. Adjacent prices/years and explicitly rejected models remain excluded. |
| A playback echo such as `5,070t` differed textually from the caption `5070 Ti`. | Comparison tokens recognise grouped digits and attached suffixes. Raw accepted user text is retained. Actual number/suffix corrections, including `Ti Super`, remain distinct and prefix trimming retains the complete corrected identifier. |
| Browser reopening exposed a reply displayed as complete but stored as stopped. | A reproduced stale-write test now requires a successful pending-to-complete database update before emitting `persistence: saved`. A stopped/stale turn produces an actionable error instead of a false acknowledgement. The original state transition was observed after service/test activity; its exact triggering process was not identified. |

## Verification

- 171 Python regressions and 79 JavaScript regressions passed, including memory
  approval, cancellation, streaming, context limits, audio encoding and cleanup.
- TypeScript check and the production build passed. No frontend source changes
  were needed for these repairs.
- Real local Qwen replays returned the correct Itanagar answer, switched from web
  workers to React, preserved `RTX 5070 Ti, RTX 5080, RTX 5090`, and answered
  Paris after an intentionally false Lyon claim, including repeated confirmations.
- Real Qwen plus a temporary SQLite database verified three pending proposals,
  explicit test approvals, recall after New chat and reopening the database,
  corrected recall after editing, and unknown preference after deletion.
- In the final browser retry, React answered correctly in 3.5 seconds and the
  database recorded the same text as complete. New chat and reopening showed
  that saved reply. Earlier stopped turns remain labelled; none were rewritten.
- Browser checks covered Nicky selection, replay/captions, Stop voice, microphone
  off, three pending suggestions with zero approved facts, New chat/reopening,
  keyboard focus and Still view. Widths of 390 and 1280 pixels had no horizontal
  overflow; captured console warnings/errors were empty. Viewport and Still view
  were restored after checks.
- Observed short, warm-model test replies took about 1.6–3.5 seconds. The saved
  long-context confirmation took 23.4 seconds; a browser React reply took 22.9
  seconds with first text at 21.8 seconds. Context, cold loading and CPU contention
  substantially change latency; these are observations, not speed guarantees.

Private replay logs, before/after test output and screenshots are in the ignored
`.june-work/conversation-audit/` folder. Private storage backups stay outside Git.

## Limits

Qwen 2.5 1.5B can still make factual, wording and instruction-following errors.
Application capability information is owned by code; general knowledge is not
made reliable by a few prompt rules or successful examples. The GDP handling is
a narrow source boundary, not a general fact-checking system. No model was
fine-tuned and no web integration was added.

Echo and interruption regressions used controlled transcripts and PCM/state
fixtures. A new human microphone conversation with this final comparison change
was not completed in this audit. Browser playback events and Stop can verify the
UI path, but cannot prove acoustic echo rejection in every room or voice quality
as heard by a person.

No roadmap progress, personality answers, selected voice or public GitHub branch
was changed by this audit.
