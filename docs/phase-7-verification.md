# June v0.6 — verification, 2026-11-08

Implementation and automated acceptance pass. **Human spoken document question and follow-up remain pending; Phase 7 build is not marked complete.** Existing acoustic and latency limitations remain open.

## Latest reliability audit

The November 9 audit of **Library + general** fixed overlapping filenames, PDF-only source requests, general questions about file formats, and mixed questions whose general clause uses a pronoun. A follow-up now stays with the latest named or cited source even after a missing answer. Deleted, ambiguous, and missing sources require clarification before June can cite a different file. Browser voice readiness now retries a transient status failure once, and the status request preserves the browser fetch receiver.

Six real local checks passed in an isolated store, including the cited GPU and VRAM facts, an unsupported serial number, a general explanation of PDF, an exact missing filename, and an answer from the unselected workshop note. The saved chat kept all six replies and was excluded from ordinary exports. Observed retrieval was about 2 ms to 1.3 s. Model-generated replies took about 24–84 s in this run, and the missing-file check returned directly. The model remains the main latency bottleneck.

**399 Python tests, 157 JavaScript tests, TypeScript, and the production build passed.** Browser checks verified that a missing filename produces a readable reply and native Heart playback without acquiring the microphone. On the final browser comparison with a missing file, Heart began at 3.96 seconds and finished at 9.93 seconds from submission. The human hands-free acceptance check remains pending.

The [earlier document-only audit](phase-7-audit.md) passed 387 Python tests, 155 JavaScript tests, TypeScript, the production build, 20 fixed real-model cases and seven adversarial cases. It introduced server-owned source quotations. That fixed set recorded a median answer time of 6.50 seconds. Its browser check took 8.7 seconds to validated text and 12.39 seconds to first audio.

## Automated checks

- 378 Python regressions passed, including 25 focused knowledge cases. Coverage includes real macOS PDF extraction, mixed/scanned/encrypted/malformed/oversized files, UTF-8 validation, upload bounds, deduplication, document/passage limits, migration/restart, cancellation, foreground priority, stale jobs, source isolation, deletion, exports, invalid citations and model outages.
- 155 JavaScript tests passed, including the late saved-chat response race, upload bridge, source scope and validated playback. TypeScript and production build passed.
- Knowledge setup downloaded all-minilm:22m and returned 384-dimensional vectors. Ollama restarted with two-model residency; Qwen selection was unchanged.
- Roadmap/workbook regenerated together: 13 phases, 97 preserved checkbox IDs. No learning/personality progress was modified.
- Live export omitted documents, passages and document conversations. No private values were printed. Pre-upgrade SQLite backup integrity passed.

## Real local model

Command: `JUNE_MODEL=qwen3:4b-instruct-2507-q4_K_M PYTHONPATH=backend backend/.venv/bin/python scripts/check-knowledge.py --run`.

Ignored report: `.june-work/knowledge-acceptance-6crp8pyi/report.json`. Fresh temporary synthetic data; no live database copy, microphone or playback.

**20/20 passed: 15 supported and five unsupported.** Relevant passages, exact source quotations, locations, scope/citation persistence, unchanged memories and model identity passed. Manual review confirmed all fixture answers, identifiers, both conflicting records and rejection of instructions embedded in a note. This bounded set does not prove unrestricted accuracy or prompt-injection resistance.

Median independent retrieval: **34.81 ms**. Median full answer turn: **23,837.36 ms**. Five tiny fixture imports reached ready in **212.61–521.57 ms**. These are observations, not speed promises.

Earlier incomplete/failed reports remain available. They exposed Darwin's unsupported address-space limit and errors when Qwen copied UUIDs or quotations. PDF extraction now has parent-enforced RSS monitoring on macOS. Model source labels are short and mapped exactly on the server. Structured quotations select whole retrieved passages (at most 600 characters); unknown labels and altered quotations remain rejected. Service outages produce retryable failures, not misleading evidence-missing answers. The final outage-path patch changes errors only; the successful evaluation's normal answer path is unchanged.

## Browser evidence

Imported the synthetic operations note using the actual file chooser, selected document mode, asked a real Qwen question with Speak replies on, received “09:40,” and observed complete native Heart playback. Clicking its citation opened the correct text and line range. After restart, the document and saved conversation scope/citations remained available.

First audio on that shared-workload run: **51.06 seconds**, ending at **52.51 seconds**. It is not an isolated latency benchmark and does not pass the earlier speed target. These browser speech observations preceded the final structured-quotation refinement; final human speech acceptance remains required.

At 375-pixel viewport width, document width was 375 pixels without horizontal overflow; the override was reset. The five-topic learning page was checked. Screenshots are under ignored `.june-work/`. Reduced-motion regressions passed; OS-level switching was not manually tested. The last production build includes citation, import-limit and restored-source-checkbox fixes; earlier UI checks do not prove every later change.

## Remaining gate

A person must deliberately enable hands-free, ask one document question and follow-up, hear complete replies, and inspect citations. The assistant never enabled the microphone. Existing recognition/echo concerns remain documented. No build/learning checkbox is completed by automated tests alone.

English-first, selectable text only; no OCR. Complex layouts and extraction failures can limit answers, with unreadable-page warnings. Valid provenance does not guarantee that every generated claim is entailed. Document answers are buffered and can be slow on this Intel Mac.

No paid provider, keys, automatic memory approval, GitHub push or public-site change. Originals/passages remain outside Git and ordinary exports/progress backups. Private recovery includes source plus ordinary data export; it does not silently back up the document library.
