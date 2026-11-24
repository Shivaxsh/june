# Phase 7 rigorous audit — 15 November 2026

Status: **complete.** Automated audit done, and the human hands-free document question plus follow-up was **passed by the user on 15 November**. Codex led the first half; the user then handed all remaining work to Claude. No commits or model/voice default changes.

## Reproduced and addressed

- Exact filename exclusions selected the rejected source as well as the requested one. Added scope regressions for corrections, quoted names, missing files, sentence boundaries, additive “not only”, content negation, and imperative “don't use”. Rejected filenames are removed before matching; ambiguous exclusions ask which source.
- “Which document mentions…” and “Any file about…” bypassed retrieval. Discovery now requires a source-content verb, preserving general passport, backup, notes-app and format questions.
- File counts could reach the model. Counts and ready-file listings now come from the actual library state.
- Short field follow-ups such as “And the budget?” could lose their source. They retain prior evidence; “the other one” asks rather than guessing.
- Claude reproduced stale refreshes held up by a slow status request, skipped refreshes after changes, and a queued refresh firing after unmount. The list refresh now runs separately, queues a follow-up and checks the mounted state.
- Deleted citations duplicated their label and still offered to open. Claude corrected the disabled-source wording; retry/cancel IDs are URL-encoded.
- A real-model build comparison emitted serialized citation metadata inside the answer string. Backend document validation now rejects leading JSON/fences before persistence or speech, and both structured prompts explicitly request plain factual prose. The client independently rejects JSON or fences after the app-owned provenance label, and envelope fields in a mixed reply's general section.

## Evidence so far

- Fresh document-only baseline: **20/20**, comprising 15 supported and five unsupported questions. Includes conflicting current/archive records, prompt injection, exact identifiers, source isolation, citation quotation/location, unchanged memories, saved scope/citations and model identity. Codex reviewed all answers against synthetic fixture facts.
- Report: `.june-work/knowledge-acceptance-1v0lzem8/report.json`; log `.june-work/phase7-baseline.log`.
- Expanded the routing fixture set from 48 to 60 cases. Citation-source rubrics now reject an otherwise plausible answer citing the rejected file; its judge regression failed before the change and passed afterwards.
- Live adversarial run in progress: `.june-work/routing-ve_lmfux`. R24 exposed the citation-metadata answer; R25 hit the 180-second limit during overlapping verification. These are findings, not passing results. Failed cases require fresh reruns after fixes with no competing heavy suite.
- Interim full JS suite: 303/303. Interim backend: 536/537; the single discovery false-positive regression was fixed while that process held the older imported code. Fresh final full-suite checks remain required after files freeze.

## Remaining

Finish adversarial cases, inspect answers and citations, rerun failures, test bounded context/output/temperature profiles without changing defaults, obtain final mutual review, run typecheck/JS/backend/build on frozen code, restart and verify a real typed document question plus citation. Human hands-free document question plus follow-up remains a separate acceptance gate; tests cannot establish human hearing or room echo behavior. Valid citations do not prove unrestricted factual entailment, and this audit cannot guarantee every possible question.

## Final pass (Claude, after takeover)

- **Inventory outage.** "How many files do I have?" reached the model when the library service was absent. It now returns the library-unavailable message; unrelated questions are unaffected. Also "1 file" and "an invoice". The regression was red before the fix.
- **Adversarial run `.june-work/routing-ve_lmfux`** (transferred, pre-fix code): 15/19. R24 was the metadata leak (fixed); R25, R30 and R59 were 180 s timeouts on a heavily loaded Mac (load average about 237 from overlapping work).
- **Final-code rerun** with nothing competing (`.june-work/routing-eazpe54a`): R08, R09, R24, R25, R30, R59 **6/6**, median 40 s. Every answer was read: R24 compares both builds as prose; R25 is mixed (Example Board A cited, RAM explained generally); R30 gives 09:40 and ignores the injected instruction; R59 "And the budget?" keeps Alpha Build.txt (1200 credits).
- **JSON parameter screen on R51** (`.june-work/routing-pkgfuo03`; request-level overrides in an isolated store, no saved defaults changed): default and four profiles passed. **ctx 2048** and **temperature 0.1** miscopied the cited value 1200 as "120" and "120 000" *with valid citations*. Defaults stay unchanged (default passed and was among the slower runs, but one case is not a basis for tuning).
- **New guard from that finding.** `knowledge_chat.miscopied_number` makes a document answer unverified when a number is a truncated or padded copy of a cited number (for example 120 or 120000 against 1200) and is not itself cited. Derived values ("by 400 credits"), separators ("1,200") and identifiers stay valid. Single digits are not compared (a known limit). The test was red first. Replaying 138 saved real cited answers from 50 reports flagged exactly the two miscopies and nothing else.
- **Final checks on frozen code**, run one at a time: `npm run typecheck` 0; `npm test` **305/305**; `npm run backend:test` **543/543**; `npm run build` 0; `git diff --check` 0. Logs: `.june-work/claude-final-{typecheck,js,backend,build}.log`.
- **Restart and live typed check.** June restarted once (Ollama untouched; reminders and timers unchanged). In the real app (headless, replies not spoken, no microphone), a synthetic Workshop Audit.md answered "10:15" and the follow-up "And the budget?" answered "740 credits", both cited to Workshop Audit.md lines 1–5. The supporting passage opened; no console errors. The test document and chat were deleted afterwards.
- **Polish noted, not changed:** copied text joins a cited value and its source badge ("7401"); the passage preview repeats the text when the quote is the whole passage.

Limits: finite synthetic tests; valid citations do not prove every claim is entailed; single-digit miscopies are not detected; answers take about 25–95 s on this Intel Mac.

## Human acceptance (15 November)

The first spoken attempts exposed three real bugs, each fixed test-first:
- Whisper-merged filenames: "workshopaudit.md" now resolves to Workshop Audit.md.
- Underscored document kinds: a resume is now found in Person_Name_Resume.pdf.
- Hands-free silence. June Audio treated the configuration change posted by Apple voice processing as device loss, killing capture and voice output. It now restarts the engine.

The user then held a hands-free session with no capture failures and no coreaudiod faults. Questions and answers: workshop start "10:15", follow-up "And the budget?" "740 credits", both cited to Workshop Audit.md. **The user confirmed hearing both replies in full and seeing correct sources.** The test note and the two chats containing only test questions were deleted; chats with the user's other speech were kept.
