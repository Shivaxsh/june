# June v0.6 implementation contract

Implement the user-approved Phase 7 plan: explicit document mode, UTF-8 text/Markdown and text PDFs only, keep documents until deletion, local embeddings and Qwen, Heart playback, no paid services. Baseline a0062dc. Existing acoustic/latency limitations remain open.

## Interfaces

Knowledge routes use /api/knowledge. GET /status returns state/message/model. GET /documents returns {documents:[{id,name,status,message,progress,pages,warning}],revision}. POST /documents accepts raw bytes with Content-Type application/octet-stream and X-File-Name (encodeURIComponent filename), bounded at 10 MiB; returns document metadata. GET /documents/{id} returns metadata plus passages [{id,text,page,lineStart,lineEnd}]. POST /documents/{id}/retry and /cancel; DELETE /documents/{id}. Errors {message}, with HTTP error status.

POST /api/chat keeps mode local/demo, adds optional knowledge:{documentIds:string[]}. Empty/invalid selection is rejected. Add events {type:'stage',stage:'searching'|'answering'} and completion citations:[{documentId,chunkId,name,page,lineStart,lineEnd,quote}], knowledgeRevision. Plain chat unchanged. No personal memory proposals or approved-memory evidence in document turns. Stored scope/citations restored through existing conversation API. Scope changes start new conversation; deleted documents cannot return through old context. UI uses citations only after done, never voices unvalidated raw model JSON.

## Constraints and steps

1. Versioned SQLite migration with pre-migration backup, private originals and bounded indexing job lifecycle. Limits: 10 MiB/file, 200 PDF pages, 50 documents, 5000 passages. pypdf extraction subprocess 60 seconds, bounded output. 600-character passages/100 overlap with page/line provenance. Partial PDFs warn; reject image-only/encrypted/malformed. Hash dedup. Explicit retry after restart; cancel/retry/delete ownership prevents stale writes.
2. all-minilm:22m embedding through local Ollama /api/embed, truncate:false, recursively subdivide oversized inputs preserving provenance; query splitting too. FTS5+cosine rank fusion/diversity, max4 passages/2400 chars. Small batches paused during voice/listening/chat/transcription. Incomplete docs never retrieve.
3. Grounded document answers: select ready IDs, collect structured Qwen answer and exact quotations, validate known source IDs and quote membership before any answer text/audio. Evidence absent or invalid -> explicit unsupported response, no general fallback. Context bounded, document instructions untrusted. Deletion cancels affected work and resets context across tabs; historical answers remain with Source deleted labels. Documents not included implicitly in exports/backups.
4. UI Documents panel and explicit Ask my documents, selection starts fresh conversation, import/progress/preview/retry/cancel/delete, accessible charcoal design. Native voice sends selected scope through same chat path. Existing voice unchanged.
5. Learning page follows embeddings/vector store/chunking/retrieval/citations. Roadmap/workbook preserve all checkbox identifiers. Test invalid files, limits, stale callbacks, deletion, migration, memory separation, citations, real20-question evaluation (15 supported/5 unsupported), regressions/build/UI and human spoken question/follow-up. Do not mark build complete without acceptance.

## Work ledger

- Baseline inspected; clean branch codex/june-v0.6 created from a0062dc.
- Backend and UI have separate write scopes; parent owns setup, documentation and acceptance evaluation.
