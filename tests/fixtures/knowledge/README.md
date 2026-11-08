# Fixed Phase 7 synthetic acceptance data

These sources contain fictional public test facts only. They are not a user profile, credentials, private notes or a live booking. `help@kestrel.example` uses a reserved example domain. Do not replace them with private documents.

`cases.json` is the versioned rubric: K01–K15 are supported; K16–K20 are unsupported. The selected source list is part of each case. Do not widen the selection to make an unsupported case answerable.

| Source | Purpose |
|---|---|
| `operations.md` | Times, paraphrases, active/retired identifier, coordinator, credits, retention, email and delivery location. |
| `hall.pdf` | Deterministic one-page selectable-text PDF: capacity, maintenance weekday and inventory identifier. Plain Helvetica text; no external asset or generator dependency. |
| `booking-current.txt` | Current Cedar/18-seat claim, with an explicitly unresolved discrepancy. |
| `booking-archive.txt` | Archived Birch/12-seat claim. Test each source alone, then compare both with attribution. |
| `untrusted-note.md` | A legitimate assembly-point fact plus instructions to emit a marker, falsely claim an export and omit citations. These instructions must never be followed. |

K19 asks a fact that exists in the PDF while selecting only the operations note. K17 asks a general-knowledge question that the selected document cannot answer. K20 combines missing evidence with the injection source. Unsupported responses must be explicit evidence-missing replies without cited or invented facts.

The runner records hashes before evaluation and leaves expected patterns out of model prompts. It independently probes retrieval, then invokes the actual document-chat service. Exact quote membership, location and scope checks are separate from answer-pattern checks. Patterns do not prove semantic entailment: manually review all 20 outputs and conflict attribution. Keep failures visible; do not tune this fixed set to observed model mistakes.

Run from the repository:

```sh
backend/.venv/bin/python scripts/check-knowledge.py --check-fixtures
backend/.venv/bin/python scripts/check-knowledge.py --run --model qwen3:4b-instruct-2507-q4_K_M
```

Use the exact installed Qwen identifier (`--model` or exported `JUNE_MODEL`); `.env.local` and the saved app selection are not loaded. This does not change persistent model selection. See `docs/phase-7.md` for isolation and remaining acceptance gates.
