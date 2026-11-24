// Spoken approval of ONE simulated purchase (docs/commerce-contract.md, Claude/Codex amendments). The browser never
// decides consent: it only (1) asks the server to arm after June's native playback of the exact review finished, and
// (2) forwards the user's next captured turn id to /voice-approve, where the server checks the transcript it observed,
// the speech onset, the one-use nonce and the quote. Voice is not identity: nothing here identifies the speaker.
import { call, defaultHttp, IntegrationError, parsePlan, type Http } from "./integrations";
import type { Plan } from "./integrations";
import { rupees, type Transaction } from "./transactions";

/** Mirrors backend june/commerce.py APPROVAL (kept in sync by a test). Full match only, after the same normalising. */
export const APPROVAL_SOURCE = "(?:(?:yes|yeah|okay|ok)[, ]+)?(?:please[, ]+)?(?:i approve(?: (?:it|this|the (?:purchase|booking|order)))?|go ahead(?: and (?:book it|place the order))?|book it|place the order|confirm (?:the )?(?:purchase|booking|order|reservation))(?:[, ]+please)?";
const APPROVAL = new RegExp(`^${APPROVAL_SOURCE}$`, "i");
const AMBIGUOUS = /^(?:yes|yeah|yep|yup|ok|okay|sure|fine|alright|all right|do it|right|correct)$/i;
// Corrections, negations, hedges and reported speech always win over approval.
const NOT_CONSENT = /\b(?:no|not|don['’]?t|do not|never|wait|stop|cancel|hold on|hang on|change|instead|but|later|cheaper|another|different|make it)\b|\b(?:he|she|they|someone|it) (?:said|says)\b|["“”‘’]|\?/i;

export type Reply = "approve" | "ambiguous" | "other";
/** How June should treat a reply to an armed review. Only "approve" may be forwarded for approval. */
export function classifyReply(text: string): Reply {
  const clean = text.replace(/^\s*(?:hey\s+)?june[,!:\s]*/i, "").trim().replace(/[.!]+$/, "").replace(/\s+/g, " ");
  if (!clean || NOT_CONSENT.test(clean)) return "other";
  if (APPROVAL.test(clean)) return "approve";
  if (AMBIGUOUS.test(clean)) return "ambiguous";
  return "other";
}
/** Spoken before re-reading the review when the reply was only "yes"/"okay". It contains no accepted approval phrase
 * (echo safety), and the server re-arms only after the full review is heard again. */
export const CLARIFY = "I need a clear approval for this exact quote. Here it is again.";

/** Which spoken review this is: placing an awaiting quote, or cancelling a confirmed simulated order. */
export type ReviewKind = "commit" | "cancel";
/** `text`: the exact review June spoke (re-read verbatim when a reply was ambiguous). `kind` defaults to "commit". */
export type Review = { transactionId: string; planId: string; revision: number; fingerprint: string; text: string; kind?: ReviewKind };

/** The only two reviews voice may arm, for this transaction's own proposed plan: a commit of a quoted or awaiting
 * quote, or a cancel of a completed order with a confirmed receipt (kept until the cancel is actually approved). */
export function reviewKind(t: Transaction, plan: Pick<Plan, "id" | "status" | "steps">): ReviewKind | null {
  if (t.planId !== plan.id || plan.status !== "proposed" || plan.steps.length !== 1) return null;
  const capability = plan.steps[0].capability;
  if (capability === "commerce.commit" && (t.status === "quoted" || t.status === "awaiting-approval")) return "commit";
  if (capability === "commerce.cancel" && t.status === "completed" && t.receipt?.status === "confirmed") return "cancel";
  return null;
}
type Expected = Review & { sessionId: string; requestId: string };
type Armed = Review & { kind: ReviewKind; sessionId: string; reviewToken: string; expiresAt: number };

/** One review at a time per hands-free session. Any new review, reply or correction disarms the previous one. */
export class VoiceConsent {
  private expected: Expected | null = null;
  private armedState: Armed | null = null;
  get armed() { return this.armedState; }
  /** A hands-free reply carrying this exact awaiting quote is being spoken as native request `requestId`. */
  expect(review: Review, sessionId: string, requestId: string) {
    this.disarm();
    if (sessionId && requestId) this.expected = { ...review, sessionId, requestId };
  }
  /** Native playback of `requestId` finished in full: the review to arm (once), if it is the expected one. */
  completed(requestId: string) {
    const due = this.expected && this.expected.requestId === requestId ? this.expected : null;
    this.expected = null;
    return due;
  }
  setArmed(review: Expected, reviewToken: string, expiresAt: number) {
    this.armedState = { transactionId: review.transactionId, planId: review.planId, revision: review.revision, fingerprint: review.fingerprint, text: review.text, kind: review.kind ?? "commit", sessionId: review.sessionId, reviewToken, expiresAt };
  }
  disarm() { this.expected = null; this.armedState = null; }
  /** Decide what to do with a captured reply. "approve" hands back the armed review (one use). "reread" hands back the
   * review to speak again after an ambiguous reply: the old token is dropped (the server already disarmed it). */
  route(text: string, sessionId: string, now: number): { kind: "approve"; armed: Armed } | { kind: "reread"; review: Review } | { kind: "pass" } {
    const armed = this.armedState;
    if (!armed || armed.sessionId !== sessionId || armed.expiresAt <= now) { this.disarm(); return { kind: "pass" }; }
    const reply = classifyReply(text);
    if (reply === "approve") { this.armedState = null; return { kind: "approve", armed }; }
    if (reply === "ambiguous") {
      const review: Review = { transactionId: armed.transactionId, planId: armed.planId, revision: armed.revision, fingerprint: armed.fingerprint, text: armed.text, kind: armed.kind };
      this.disarm();
      return { kind: "reread", review };
    }
    this.disarm();  // a correction, question or anything else goes to chat normally; the old review is void
    return { kind: "pass" };
  }
}

const invalid = () => new IntegrationError("June returned an unexpected voice review reply.", 502, "invalid-response");

/** Ask the server to arm voice approval for the review June just finished speaking (native request id). */
export async function arm(review: Review & { sessionId: string; requestId: string }, http: Http = defaultHttp) {
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(review.transactionId) || !/^[a-f0-9]{32}$/.test(review.planId) || !review.sessionId || !review.requestId)
    throw new IntegrationError("Voice approval isn’t available for this review.", 400, "invalid-input");
  const data = await call(http, `/api/transactions/${review.transactionId}/arm`, {
    planId: review.planId, revision: review.revision, fingerprint: review.fingerprint, sessionId: review.sessionId, requestId: review.requestId });
  if (typeof data.reviewToken !== "string" || !/^[A-Za-z0-9_-]{8,128}$/.test(data.reviewToken) || typeof data.expiresAt !== "number") throw invalid();
  return { reviewToken: data.reviewToken, expiresAt: data.expiresAt };
}

/** Forward the captured turn: the server, not this client, checks the transcript, onset, nonce and quote. */
export async function voiceApprove(armed: Armed, turnId: number, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  if (!Number.isSafeInteger(turnId) || turnId < 1) throw new IntegrationError("That reply can’t be used for approval.", 400, "invalid-input");
  const data = await call(http, `/api/plans/${armed.planId}/voice-approve`, {
    requestId: uuid(), revision: armed.revision, fingerprint: armed.fingerprint, reviewToken: armed.reviewToken, sessionId: armed.sessionId, turnId });
  const plan = parsePlan(data.plan);
  if (!plan) throw invalid();
  return { serverNow: data.serverNow as number, plan };
}

const FINAL = new Set(["completed", "unknown", "cancelled", "expired"]);
/** A cancel's outcome is the cancellation (or unknown): the still-completed order it started from is not final. */
const CANCEL_FINAL = new Set(["unknown", "cancelled"]);
/** After a voice approval: read the transaction until its outcome is final (bounded). Read-only: never commits again. */
export async function waitForOutcome(id: string, read: (id: string) => Promise<{ transaction: Transaction }>, { kind = "commit" as ReviewKind, timeoutMs = 30000, intervalMs = 1000, sleep = (ms: number) => new Promise(r => setTimeout(r, ms)), now = () => Date.now() } = {}) {
  const final = kind === "cancel" ? CANCEL_FINAL : FINAL;
  const until = now() + timeoutMs;
  let last: Transaction | null = null;
  while (true) {
    try { last = (await read(id)).transaction; if (final.has(last.status)) return last; } catch { /* keep the last known state */ }
    if (now() >= until) return last;
    await sleep(intervalMs);
  }
}
/** What June says once the simulated outcome is known. Only a verified receipt is described as done. */
export function outcomeSpeech(t: Transaction | null, kind: ReviewKind = "commit") {
  if (kind === "cancel") {
    if (t?.status === "cancelled" && t.receipt && t.receipt.status !== "confirmed")
      return `Cancelled.${t.domain === "dining" ? "" : ` Simulated refund: ${rupees(t.receipt.totalMinor)}.`} Nothing real was charged.`;
    return "I couldn’t confirm the cancellation yet. I won’t send it again; check the booking card.";
  }
  if (t?.status === "completed" && t.receipt?.status === "confirmed")
    return `Done. Simulated receipt: ${t.receipt.detail}${t.domain === "dining" ? ", no charge" : `, ${rupees(t.receipt.totalMinor)}`}. Nothing real was charged.`;
  if (t?.status === "cancelled") return "That simulated booking was cancelled. Nothing was charged.";
  if (t?.status === "expired") return "That quote expired before it could be completed. Nothing was booked. Ask me for a fresh quote.";
  return "I couldn’t confirm the outcome yet. I won’t place it again; check the booking card.";
}

/** A 4xx from voice-approve: the server refused before approving (bad turn, stale review, not a go-ahead). Anything else
 * (network failure, 5xx, unreadable reply) may have happened after the commit, so it is never treated as "nothing booked". */
export function isDefiniteRejection(failure: unknown) {
  return failure instanceof IntegrationError && failure.status >= 400 && failure.status < 500;
}
const BEFORE_COMMIT = new Set(["collecting", "choosing", "quoted", "awaiting-approval", "expired", "cancelled"]);
/** What June says when voice approval failed, given the transaction as read back afterwards (read-only).
 * A verified receipt is spoken as done; "Nothing was booked" only for a definite refusal of a booking read as uncommitted. */
export function approvalFailureSpeech(failure: unknown, t: Transaction | null, kind: ReviewKind = "commit") {
  if (kind === "cancel") {
    if (t?.status === "cancelled") return outcomeSpeech(t, "cancel");
    if (isDefiniteRejection(failure) && t?.status === "completed" && t.receipt?.status === "confirmed")
      return `${failure instanceof Error ? failure.message : "Voice approval didn’t go through."} Nothing was cancelled.`;
    return outcomeSpeech(t, "cancel");
  }
  if (t?.status === "completed" && t.receipt?.status === "confirmed") return outcomeSpeech(t);
  if (isDefiniteRejection(failure) && t && BEFORE_COMMIT.has(t.status) && !t.receipt)
    return `${failure instanceof Error ? failure.message : "Voice approval didn’t go through."} Nothing was booked.`;
  return "I couldn’t confirm whether that went through. I won’t try it again; check the booking card.";
}
