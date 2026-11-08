# Phase 7 — Knowledge from your documents

June v0.6 adds explicit **Ask my documents** mode: import a small private collection, select ready sources, then inspect the passages behind an answer. The implementation contract is [phase-7-implementation.md](phase-7-implementation.md). Delivery acceptance is **pending** until the [verification report](phase-7-verification.md) contains actual results, including the human spoken check. Existing recognition, echo and latency limitations remain open.

## Use the document library

1. Start June as usual on port **3001**. Run `npm run knowledge:setup` once if the local embedding model is missing. This installs/verifies **all-minilm:22m**; it does not replace the configured Qwen model or Heart voice.
2. Open Documents and import a UTF-8 `.txt`/`.md` or a PDF with selectable text. Limits are **10 MiB/file, 200 PDF pages, 50 documents and 5,000 passages**. There is no OCR. Unsupported, malformed, encrypted and image-only inputs are rejected; a partly searchable PDF needs a warning identifying pages without text.
3. Wait until indexing reports ready. Imports are serial; indexing pauses between small batches during listening, transcription, chat and playback. Cancel stops indexing; interrupted jobs require explicit Retry after restart. Identical file hashes deduplicate imports.
4. Choose one or more ready sources and enable **Ask my documents**. Selecting a different scope starts a fresh conversation. Ordinary chat keeps its existing behaviour and does not silently search documents.
5. Send a typed or spoken question. Searching documents and Preparing sourced answer indicate real stages. The answer is held until its citations validate. Open each citation to inspect the filename and PDF page or note line range. Missing or invalid evidence produces an explicit unsupported answer.
6. Delete a source when it is no longer needed. This removes its original, passages and vectors and cancels affected work. Earlier written answers remain visible with Source deleted labels; they must not reintroduce deleted evidence in a new turn.

Documents remain until explicit deletion, independently of the existing 30-day chat retention. Originals and extracted passages do not belong in ordinary chat/memory exports, progress backups or Git. Document statements never automatically become approved personal memories; approved memory is not evidence in document mode. Do not import private files to produce acceptance evidence.

## Learn in workbook order

The [roadmap](roadmap/building-june.html), [workbook](roadmap/June%20Build%20Workbook.md#phase-7) and `/learn/phase-7` follow the same five topics:

| Topic | Implementation and practice |
|---|---|
| Embeddings | Local all-minilm:22m maps text into vectors. Send `truncate:false`; subdivide oversized passages and long queries rather than silently dropping their ending. |
| Vector storage | Private SQLite holds vectors, source IDs, metadata and indexing ownership. A versioned migration keeps a private pre-migration backup. Chroma/pgvector are alternatives to study, not required services. |
| Chunking | Start near 600 characters with 100-character overlap, retaining source boundaries, PDF page and note line locations. |
| Retrieval and reranking | Fuse FTS5 keyword rank and cosine-similarity rank, apply diversity selection and keep at most four passages within 2,400 evidence characters. Incomplete or unselected documents cannot retrieve. |
| Citations | Qwen selects supplied source labels; the server attaches exact stored passages and validates membership before showing or speaking text. This avoids generating copied quotations. A matching quote proves provenance, not that every answer claim follows from it. |

Retrieved instructions are untrusted source text. They cannot authorise exports, execute actions or override the user/system instructions. A conflicting-source answer must attribute the records and their discrepancy rather than silently invent a resolution.

## Runtime and measurements

The runtime launcher configures **`OLLAMA_MAX_LOADED_MODELS=2`**, allowing the small embedding model and Qwen to remain resident together. This reduces repeated model swapping but increases memory pressure on the Intel Mac. It does not promise concurrency throughput or faster answers; cold loads, CPU contention, memory pressure and background work can increase latency. Foreground work still takes priority over indexing. Restart the model runtime for a changed launcher setting to take effect; editing the script does not change a running Ollama process.

Setup verified on 2026-11-08: all-minilm:22m downloaded and returned **384 dimensions**. Ollama restarted with two-model residency. The fixed 20-question real-Qwen evaluation passed; measurements and remaining human acceptance are in the verification report.

Record import/extraction/indexing, retrieval, generation and first-audio timing separately. The acceptance runner measures import-ready, retrieval and answer-turn durations, with a generation estimate from stage boundaries where available. It does not start Heart, record sound or measure first audio. Human/parent verification supplies first-audio measurements and audible-completion evidence.

## API contract

The same-origin document API lives at `/api/knowledge`. Errors contain `{message}` and an appropriate HTTP error status.

| Method/path | Contract |
|---|---|
| `GET /status` | Readiness state, message and embedding model. |
| `GET /documents` | `{documents:[metadata], revision}`. Metadata includes id, name, status, message, progress, pages and warning. |
| `POST /documents` | Raw bytes, `Content-Type: application/octet-stream`, URI-encoded `X-File-Name`; returns document metadata. |
| `GET /documents/{id}` | Metadata and `{id,text,page,lineStart,lineEnd}` passages. |
| `POST /documents/{id}/retry` or `/cancel` | Explicit indexing lifecycle controls. |
| `DELETE /documents/{id}` | Remove document content and invalidate affected context. |

`POST /api/chat` retains `mode: local|demo` and adds optional `knowledge:{documentIds:[...]}`. Empty/invalid document selection is rejected. Stage events use `searching` and `answering`; completion carries validated `citations:[{documentId,chunkId,name,page,lineStart,lineEnd,quote}]` and `knowledgeRevision`. Persisted conversations restore scope and citations. Only validated completion text may be voiced; raw model JSON must not be shown or spoken.

## Run the fixed local acceptance set

From the June repository, with its Python environment and the existing models installed:

```sh
backend/.venv/bin/python scripts/check-knowledge.py --check-fixtures
backend/.venv/bin/python scripts/check-knowledge.py --run --model qwen3:4b-instruct-2507-q4_K_M
```

The runner does **not** load `.env.local` or read the live database/saved model selection. Use `--model` with the exact installed Qwen identifier used by June, or explicitly export `JUNE_MODEL` (and `OLLAMA_BASE_URL` if using a different local port) in the shell. `--model` overrides `JUNE_MODEL` for this run only; neither option persists a model selection. Without either, the backend default may name an older model that is not installed. The example above uses the parent-confirmed existing model; it does not install or switch the application model.

The first command checks fixture structure and does not call Ollama or import backend services. The second explicitly opts into real local embeddings and Qwen. It constructs services directly in a fresh temporary data directory, imports only the five checked-in synthetic files, and never reads, clones or writes the live June database. It does not start the app lifespan, microphone, native audio, another server, or model setup. Model/runtime settings are not changed. The same installed Ollama runtime is used, so run separately from interactive June work.

Reports go under ignored `.june-work/knowledge-acceptance-<unique-run>/report.json` with private permissions. The temporary database and originals are removed after the run. Output records fixture/source hashes, configured and observed model identity, per-case events, retrieved passages, answer/citation checks and timings. Unsupported answers must match the backend’s explicit evidence-missing response without added facts. Persisted scope/citations and absence of memory writes are also checked. An interrupted or blocked run remains incomplete, never a pass. Missing models or unavailable direct backend APIs produce a nonzero exit and an explanatory report. Use `--timeout` to bound each indexing/question operation.

The set is fixed at **15 supported and five unsupported questions**, covering paraphrases, active/retired identifiers, note and PDF locations, independently selected conflicting records, a two-record discrepancy, injection and an out-of-scope fact. The lightweight answer-pattern checks are conservative aids, not a semantic judge. Review every answer and quote manually; do not rewrite fixtures to fit a model's mistakes. A retrieval check runs independently before each answer, so it measures repeat retrieval and does not claim to capture the exact internal generation evidence unless citations confirm it.

This runner does not replace lifecycle/limits/migration/delete-during-generation regressions, UI/accessibility checks, a production build, persisted restart acceptance or a human spoken question plus follow-up. Keep those gates pending until their actual checks run. Mark only Phase 7's build after all acceptance gates pass; leave learning checkboxes and personality answers unchanged.

## Maintain the roadmap

Edit `docs/roadmap/source/building-june.source.html` and matching Phase 7 exercises in `docs/roadmap/source/workbook.py`, then run:

```sh
python3 docs/roadmap/source/build.py
```

This generates the roadmap, workbook, phase data and overview together and checks the 13-phase/97-checkbox invariant. Preserve the existing checkbox identities and `building-june-progress-v2` storage key. Documentation generation never checks a completed item or edits browser progress/personality answers.
