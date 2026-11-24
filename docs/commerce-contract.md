# 8.8 implementation contract — simulated commerce

User approved 22 November 2026. Codex owns backend commerce, adapters, API, library_chat integration and backend voice provenance. Claude owns lib/transactions.ts, components/transactions/**, commerce UI in Chat/Systems, frontend voice client and JS/UI tests. One release owner: Codex. No real merchants, credentials or charges. Existing Qwen4B/4096/Heart/grants preserved.

## HTTP (version 1 envelope, serverNow milliseconds)
- GET /api/transactions -> {version,serverNow,transactions:Transaction[],preferences:Record<string,string>}
- POST /api/transactions/respond {requestId,conversationId,text} -> {version,serverNow,reply,transaction?:Transaction,plan?:Plan}; same deterministic service is called from normal June chat. conversationId is a bounded opaque conversation or temporary-session id. requestId is UUID/idempotency key. This endpoint ONLY prepares/updates drafts or checks receipts; approval uses plan engine.
- GET /api/transactions/{id} -> {version,serverNow,transaction}
- POST /api/plans/{pid}/voice-approve {requestId,revision,fingerprint,reviewToken,sessionId,turnId} -> existing plan envelope. Server validates emitted transcript/onset and consumed nonce. Client cannot invent voice:true.
- POST /api/transactions/{id}/arm {planId,revision,fingerprint,sessionId,requestId} -> {version,serverNow,reviewToken,expiresAt}. Arming is accepted only after backend native playback-end for this exact quote summary/session/request; frontend requestId is the native voice playback request UUID string. No arming from client playback-end booleans. Native backend bridge details coordinated before frontend integration.

## Types
Transaction: {id,conversationId,domain:'retail'|'tickets'|'dining',status:'collecting'|'choosing'|'quoted'|'awaiting-approval'|'executing'|'completed'|'unknown'|'cancelled'|'expired',simulated:true,slots:Record<string,string|number>,missing:string[],offers:Offer[],quote:Quote|null,planId:string|null,receipt:Receipt|null,lastReply:string}
Offer: {id,title,merchant,description,totalMinor:number,currency:'INR',available:boolean,seats?:string[]}
Quote: {id,revision,fingerprint,merchant,currency:'INR',totalMinor:number,lines:{label,quantity,unitMinor,totalMinor}[],terms:string,expiresAt:number,selection:Record<string,string|number|string[]>,summary:string}
Receipt: {id,transactionId,status:'confirmed'|'cancelled',simulated:true,totalMinor:number,currency:'INR',createdAt:number,detail:string}

All money integer paise. All offers and receipts explicitly simulated. Immutable quote fingerprint binds selections/price/terms; material changes expire old plan and require review. Commit idempotent per quote and atomic with fixture inventory/price validation. Unknown -> read receipt, never replay. Cancellation prepares a separate exact-reviewed plan/refund; stop is not cancellation of completed purchase. Transactions outside saved chat use stable temporary-session ID; do not write normal chat history from panel actions.

Frontend typed/button approve via existing plans APIs and exact fingerprints. Voice accepts only explicit action phrases (I approve/go ahead/yes book it/place the order), no amount/code repetition; bare yes/okay -> clarification. Server armed nonce expires min(60s,quote expiry), one current quote per voice session. No speaker identity claim. No native playback-end / healthy echo provenance => voice approval unavailable, typed/button fallback. Existing financial risk remains never rememberable.

All three fixtures: retail cart, cinema geometry (contiguous central block about65% back), dining reservation zerocharge. Explicit location required; weather city only after confirmation. User says remember to persist preferences; otherwise task-local. Ask only missing material slots; quote before executing. No automatic substitutions or group splitting. Deterministic app-owned replies, no model-written receipts.
