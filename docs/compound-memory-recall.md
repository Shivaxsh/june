# Compound approved-memory recall repair — 2 November 2026

## Recorded failure

A real compound request for saved age, name, location, gender self-description and an explanation bypassed the narrow recall grammar. Lexical retrieval supplied only the location fact; the model denied knowing the user's information. The immediate explicit memory-check follow-up retrieved no facts and produced another false capability denial. The approved records were intact. This was an application routing/retrieval failure, not lost data or a measured hardware limitation.

## Repair

- Parse complete personal-recall clauses joined by commas, conjunctions and an optional source-explanation request. Every substantive clause must be recognised; an unrelated explanation or drafting task is not silently dropped.
- Resolve an explicit memory-check follow-up to its immediately referenced personal request, including after an incorrect model denial. Stop at a topic change. Ask which detail is wanted when the reference cannot be resolved, without disclosing unrelated data.
- Read approved fields directly from SQLite, with exact saved quotations and source labels. The model does not decide whether the database can be read.
- Return known facts alongside explicit missing-field notices. Conflicting approved values require Memory review rather than an arbitrary model choice. Pending proposals are not approved facts.
- Quote a saved age/self-description as historical user text. Explain that gender is not inferred from a name, age or location. Do not recalculate a current age or change the user's description.

Current corrections retain their existing priority and still use the context path. Mixed non-recall tasks, source documents and fictional/quoted prompts retain the ordinary model path. This improves a defined recall grammar; it is not a claim that all possible wording or all model answers are reliable.

## Verification

Five new regressions failed before implementation and cover the exact compound wording, recovery after a model denial, missing fields, unknown gender, alternative list phrasing and a topic boundary. Existing missing/ambiguous-record tests now require explicit application responses, no model calls and unchanged approved/pending records. The full final Python run passed **324 tests** in 27.317 seconds. No frontend source or API shape changed.

After restarting the backend, the exact compound question was submitted through the existing June browser conversation with Qwen3 4B still selected. It returned three distinct approved records (one self-description covers two requested fields), the Memory provenance explanation and no unasked colour fact. Text completed in about 0.1 seconds; the first playback event was 923 ms after submission. The exact memory-check follow-up then returned the same approved records in about 0.3 seconds, with first playback at 481 ms. Nicky playback completed for both; microphone capture stayed off. These are typed-request/browser-event observations, not new microphone latency measurements.

The live database's integrity check returned `ok`; its four approved memories were unchanged. Original conversations and their earlier incorrect replies remain visible, with corrected replies appended. A private screenshot is retained under `.june-work/compound-recall/verified.png`; it is not committed because it displays personal facts. No public hosting or model selection was changed.
