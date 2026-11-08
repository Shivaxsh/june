# Phase 7 reliability audit — 2026-11-08

Automated and typed-browser checks passed after the repairs below. **Human hands-free acceptance remains pending. Phase 7 build stays unchecked.** This work changes application behaviour and tests; it does not train model weights or establish perfect accuracy.

## Reproduced defects and repairs

- A running extraction continued when foreground listening started. Extraction now participates in cancellable background ownership, waits for foreground work to finish and retries safely. A regression verifies cancellation within 0.5 seconds and successful retry.
- Unavailable document storage could stop the whole application at startup. Document readiness now fails explicitly while ordinary chat and voice remain available.
- A document shutdown failure could skip microphone/process cleanup. Shutdown attempts every subsystem release, then reports the first failure. A regression injects the failure and verifies native audio cleanup still runs.
- Extremely large numeric embedding values could raise an unhandled overflow. Invalid vectors, including huge integers, are rejected as safe service errors.
- Malformed citation labels could reach dictionary membership with unhashable values. Label types and exact object fields are now checked first.
- Generating full source quotations wasted model output and CPU time. Qwen now selects only request-local source labels; the server attaches the exact stored passage and validates it before releasing text or speech. The public citation event contract still includes quotation, filename and location. This deliberately adapts the original model-generated-quotation plan: provenance comes from storage, while semantic support still requires evaluation. Unknown labels and model-supplied quote fields fail closed.
- A legacy forced-timeout test could kill its child fixture before startup on a busy machine. The test waits for the real child to initialise before exercising termination/escalation; production timeout settings are unchanged.

## Regression and boundary coverage

**387 Python tests and 155 JavaScript tests passed. TypeScript and the production build passed.** Nine new audit tests extend the existing 25 knowledge tests. Coverage includes foreground pre-emption, invalid scopes, unavailable storage, cleanup failure, numeric extremes, malformed labels, canonical quotations, Unicode chunk reconstruction at eleven boundary lengths, BOM/CRLF/uppercase names and a real 200-page partial PDF.

Existing regressions cover malformed/encrypted/scanned/mixed PDFs, import size and passage limits, duplicates, cancellation/restart recovery, unavailable embedding models, invalid citations, source isolation, deletion during generation, stale callbacks, retention, memory, speech ordering and cancellation. Passing regressions do not prove every device/browser combination.

Ignored evidence logs: `.june-work/audit-python-final.log`, `audit-js-final.log`, `audit-typecheck.log`, `audit-build.log` and `audit-citations-green.log`. The final test-only refinement removes an extra field from the malformed-label test so it directly exercises label validation.

## Real model evaluation and parameter comparison

The installed `qwen3:4b-instruct-2507-q4_K_M` and `all-minilm:22m` were retained. Evaluations used fresh temporary synthetic stores, never a copy of private chats or documents.

- Fixed acceptance: **20/20** — 15 supported questions, five explicitly unsupported. Reviewed all answers, including current/retired identifiers, note/PDF locations, conflicting records and embedded malicious instructions. Source scope/citation persistence, unchanged memory and model identity passed. Report: `.june-work/knowledge-acceptance-461sf8fl/report.json`.
- Extra stress set: **7/7** — unannounced document injection, misleading identifier premise, two requested facts, requests to guess unsupported facts, a long query and broad source selection. Report: `.june-work/knowledge-stress-6b3944ih/report.json`. The first stress run flagged a correct explanation because the inherited rubric forbade any mention of a retired code. The rubric was corrected to reject calling it active, then all seven cases were rerun; no model answer was patched to fit the test.
- Before the quotation optimisation, four profiles each passed the same five-case subset. No persistent model settings were changed:

| Profile | Temperature | Context | Output cap | Passes | Observed median answer |
|---|---:|---:|---:|---:|---:|
| Default | 0 | 4096 | 1024 | 5/5 | 26.02 s |
| Compact context | 0 | 2048 | 1024 | 5/5 | 25.86 s |
| Warmer | 0.2 | 4096 | 1024 | 5/5 | 65.10 s |
| Shorter output | 0 | 4096 | 512 | 5/5 | 48.27 s |

These profiles ran under varying shared workload; the times are observations, not an isolated causal benchmark or reason to adopt a parameter. Defaults remain temperature 0, context 4096 and output cap 1024. Report: `.june-work/knowledge-parameters-7sfmep7i/summary.json`.

After server-owned quotations, the final full 20-case set measured **6.497 s median answer turn** and **22.08 ms median independent retrieval**. The previous full-set median was 23.84 seconds, under different workload conditions. Do not present that comparison as a guaranteed speed-up. Retrieval is measured separately; buffering for citation validation remains intentional. Repeatable opt-in runners are `scripts/check-knowledge.py`, `scripts/check-knowledge-parameters.py` and `scripts/check-knowledge-stress.py`.

## Real browser and existing-data checks

- Uploaded a disposable synthetic note through the actual file chooser. Preview displayed script/image markup as literal text; no injected image element was created. Unicode remained readable.
- Keyboard Space operated Still view. At 375 pixels, document width was 375 pixels without horizontal overflow; the temporary viewport override was removed. Reduced-motion regressions passed; an OS-level preference change was not performed.
- Deleting only that audit note removed its open preview in a second tab and invalidated context. Pre-existing document IDs were unchanged. The temporary second tab was closed.
- The restarted application answered “What time does the Kestrel workshop close?” with **17:20**. Its citation opened `operations.md`, lines 1–10, containing the supporting statement. Native Heart playback reported complete, then the UI returned to Idle. No browser warning/error entries were captured in the final check.
- That final browser turn measured **8.7 s to validated text**, **12.39 s to first audio**, **3.65 s native first-segment preparation**, and **13.75 s to final audio end**. These are one-turn UI observations. They do not establish human-perceived audio quality, microphone reliability or a latency percentile.
- Ordinary approved-name recall still used the approved-memory path. Approved facts and personality matched the private pre-audit backup; they were not printed or modified. No automatic memory approval was introduced.

Screenshots remain private under ignored `.june-work/audit-final.png` and `.june-work/audit-safe-preview-mobile.png`. Documents, passages, recordings and reports are excluded from Git and ordinary data exports. Published branches and the public static site were not changed.

## Remaining acceptance

- A person must enable hands-free, ask a sourced document question and follow-up, hear complete Heart replies and inspect citations. The assistant did not enable microphone capture during this audit.
- Physical speaker echo, fan noise, device changes and interruption quality require the human room check; synthetic/automated tests cannot certify them.
- The earlier median ≤3.5 s / p95 ≤6 s conversational target is not established. The measured document turn exceeds it; no new speed promise is made.
- Valid provenance does not guarantee every generated claim follows from the source. English-first, selectable-text-only extraction and small-model limitations remain.

No known reproduced blocking defect remains from this bounded automated/typed audit. This is not a claim that all possible defects are absent. Keep Phase 7's build and learning checkboxes unchanged until the remaining acceptance is completed.
