# Phase 6 · Memory and personality · v0.5

Open June at http://127.0.0.1:3001. Existing model, speech setup and start commands stay the same. Run `npm run build` before `npm start` after upgrading. No database server, embedding model, account or paid service is required.

## First use

1. Send a real local message containing a useful personal fact. After the reply and speech finish, June may propose up to three facts in **Memory**. Invalid model output produces no suggestions.
2. Review the exact supporting quotation. **Approve** saves the displayed fact. **Edit and approve** lets you choose the wording and explicitly replace a conflicting fact. **Reject** suppresses that proposal within the conversation. You can also add a fact manually.
3. Start **New chat** and ask about the fact. Expand **Approved facts provided** below the reply to inspect the facts selected by the server. Explicit personal-detail questions use approved facts directly. Other model answers can still be incorrect; providing a fact does not prove the model used it.
4. Open **Recent chats**, search message text and reopen a conversation. Stopped/failed replies remain labelled and are excluded from future model context. New chat does not delete these saved conversations.
5. Edit or delete a saved fact. June cancels generation, queued/current speech and hands-free capture; other tabs receive an immediate change notification with a 1.5-second revision-poll fallback. Visible chats remain separate. Earlier turns are excluded from future inference after a context reset.
6. Open **Personality**, edit the ten workshop fields, choose steady/calm/bright and save. Voice identity is unchanged; rates are 0.98/0.92/1.04 at ordinary pitch. The profile never grants tools or makes the model learn permanently.
7. Under **Export or import private data**, optionally include chats in an export. Import a June JSON export or Building June progress export, inspect the preview, then explicitly save. Workshop imports affect personality only, never roadmap progress. Imported chats are viewable but excluded from inference context.

## Storage and retention

Default private directory: `~/Library/Application Support/June/data/` (`0700` directory, `0600` SQLite file). `JUNE_DATA_HOME` in `.env.local` can override it; keep this outside the repository. Python uses built-in sqlite3, versioned `PRAGMA user_version` migrations and transactions. No audio is stored by this phase. Personal data remains local, unencrypted at the SQLite layer; macOS account/disk protection governs access. JSON exports contain private data.

Conversations expire 30 days after the last activity, with cleanup at startup, during access and every minute. Pending suggestions expire with their conversations. Approved facts and personality persist. Deleting a memory does not delete its source chat. Delete that chat separately or let it expire. Clear history keeps approved memories/profile. Deletion is logical application deletion; external backups and previously exported files are separate.

Database failures are explicit. The composer blocks until storage works or you choose **Continue in temporary chat**. Temporary chat excludes persisted memory/personality and is not saved. The choice is not persisted across reload. A server-side write error cannot be represented as a successful saved reply.

## Source map and flow

- `backend/june/memory.py`: migrations, retention, validation, transactions, deduplication, lexical retrieval, profile, import/export.
- `backend/june/memory_service.py`: foreground priority, cancellation, fixed-prompt boundaries, saved turn streaming, local model extraction.
- `backend/june/memory_api.py`: bounded CRUD and review APIs; `app/api/library/[...path]/route.ts` is the allowlisted same-origin bridge.
- `components/memory/`: typed client state, cross-tab invalidation and review controls.
- `components/Chat.tsx`: conversation/turn IDs, optional completion metadata, suggestions only after completed real replies.
- `lib/voice/speech.ts`, `lib/orb/renderer.ts`: expression rate and restrained idle expression; Still view is static.
- `/learn/phase-6`: all seven workbook topics, in the same order.

Browser → same-origin Next bridge → Python authoritative history and context revision → up to eight whole approved facts within 1,600 characters → fixed prompt + bounded personality + recent completed turns → local Qwen → NDJSON → written reply / sentence speech queue. The server saves status before confirming completion. Optional `conversationId` and `turnId` protect duplicate writes; legacy no-ID requests remain temporary and cannot replay pre-reset history.

Extraction is cancellable low-priority inference, never detached from its request. Exact personal clauses become pending proposals when a completed reply is saved, without another model call. Ambiguous extraction starts after completed real replies and speech playback, waits out the hands-free follow-up window, can time out after 30 seconds, and yields to new chat inference. Listening/Stop/New chat/navigation cancel it. The model must copy exact user clauses with supporting quotes; credentials, fiction and unsupported paraphrases are rejected. Exact matching is intentionally conservative and may miss useful facts. Conflict detection catches explicit identity/preference statements; all replacements require a user-selected target, and no automatic overwrite exists.

## Verification

`npm test`, `npm run backend:test`, `npm run typecheck`, `npm run build`. Tests use temporary SQLite directories; never point tests or fixtures at private user data. See `phase-6-verification.md` for actual checks and remaining limitations. Keep Phase 5’s separate human-microphone completion gate unchanged.

The saved profile permits ten fields of up to 500 characters each. To protect the small model's context, the prompt includes complete fields within a 1,600-character profile budget, prioritising speech, boundaries and address. Longer lower-priority fields remain editable but may not enter a reply. Keep workshop answers brief. At most 100 recent chat summaries appear at once; search can locate older retained chats. Chat exports include all retained conversations. Imports are bounded to 2 MiB and 500 conversations at a time.

## Response latency and memory review

Saved context keeps at most nine whole completed turns and 4,000 UTF-16 characters. When shortening is needed, it advances in four-turn blocks; short conversations are unchanged, and typical long chats supply six to nine recent turns. Large individual turns can reduce that count further. Older messages remain viewable but do not become approved memory. The block window reduces repeated CPU prompt processing; cold model loads and a window advance can still take longer. Relevant approved facts are presented in a stable order. See [the follow-up repair report](voice-followup-repair.md).

Memory displays approved and awaiting-review counts separately. If a name is transcribed incorrectly, use Edit and approve to correct it. Facts beyond the three suggestions for a single reply can be added manually. June cannot silently approve these facts herself.
