# June next pass — recent-chat findings (2026-11-13)

Status: implementation and automated verification completed on 2026-11-13; the user subsequently confirmed wake phrase, interruption and echo handling worked in their hands-free test. See the final handoff entry for evidence and latency limitations.

## Evidence and priority

The visible recent conversation shows ordinary outfit advice incorrectly answered as missing document evidence. A general-answer follow-up succeeds; a later correction is acknowledged. One earlier turn is marked stopped, which alone does not prove a fault. The capability answer describes unsupported tools honestly but omits connected document, voice and approved-memory features. Do not copy private conversation text into fixtures or reports.

Latest visible timings: first text 18.0s, first audio 22.0s, completion 42.7s. These are observations from one turn, not a latency benchmark. Previous recorded checks: typecheck/build exit 0, JavaScript 183/183, backend 436/436. No suites rerun for this planning-only pass.

## 1. Fix advice versus personal-record routing

Owner proposed: Codex, continuing the explicit handover of `backend/june/library_chat.py` and its tests. Claude cross-reviews.

Likely cause verified in code: `may_use_documents` treats ownership words such as “my” as a reason to retrieve; `compose_reply` then suppresses general fallback for any `PERSONAL` wording. This conflates advice about a user's situation with a question about their stored records. Reproduce before choosing the narrowest fix; do not simply remove all personal-record safeguards.

- Add synthetic cases: “What should I wear to my ceremony in a warm coastal town?”, packing for my trip, planning my study routine, and a conversational gender/style correction.
- Contrast with “What size is on my saved order?”, explicit document requests, personal fact recall, and a missing document fact. Those must remain evidence-bound or honestly unknown.
- Test both retrieval with irrelevant passages and no relevant passages; general advice must remain useful without a “say it generally” repair.
- Exercise compound inputs and follow-ups without dropping the current conversation or overriding the user's latest correction with approved memory.
- Pass condition: correct provenance and useful general response for advice; valid citations for sourced facts; no invented personal facts or automatic memory approval.

## 2. Make capability answers complete and consistent

Owner proposed: Claude for `backend/june/app_info.py` / relevant prompt and tests; agree before concurrent edits. Codex owns isolated harness cases.

- Cover paraphrased and compound questions, not just an exact full-string question.
- Include actual document Q&A, approved memory, local voice and text capabilities; clearly state unsupported external actions.
- Prevent broad capability matching from intercepting quotations, translation, fiction or genuine user tasks.
- Investigate the malformed contraction seen in the capability response with a synthetic regression if reproducible.

## 3. Verify the user's original hands-free failure

Codex traces backend/audio stages; Claude handles interface feedback and layout. Keep one app and one inference job at a time.

With the user present, test wake phrase → captured speech → visible transcript → answer → audible output. Then interruption, immediate follow-up, silence, echo, Stop, and New chat. Record stage timings and failure states, without raw private utterances. Readiness flags and unit tests do not establish microphone-to-answer success. Verify progressive audio after the final speech-validation guard, including a document reply that must wait for validation.

## 4. Measure latency and finish responsive acceptance

- Codex: repeat identical cold and warm inputs on the same Qwen model, with unrelated heavy jobs stopped. Separate retrieval, model load, first token, synthesis and playback delay. Keep existing defaults until repeated correctness and latency evidence supports a change.
- Run the full 40-case routing baseline once on the final corrected code; prior targeted passes and parameter screening are not a clean final 40/40 run. Add the new synthetic advice and capability cases, keeping original IDs stable.
- Claude: real 375/760/1100px and desktop checks; page scrolling over the orb, composer reachability, drawer navigation, no horizontal clipping, touch cancellation and reduced motion. Resolve the preview width control reset or use a reliable viewport before claiming acceptance.

## 5. Finish and checkpoint

Cross-review changes; run focused regressions first, then `npm run typecheck`, `npm test`, `npm run backend:test`, `npm run build`. Restart the single app after backend changes; repeat real typed/spoken flows. Append exact results and remaining limitations to `docs/handoff.md`. Preserve all existing uncommitted work; no commit or model/provider switch is part of this prepared plan.

Start with step 1, then step 2. The spoken test needs the user; independent routing, capability and viewport work can be prepared first. File ownership must be acknowledged in both agent chats before concurrent implementation resumes.
