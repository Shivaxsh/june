// 8.8 simulated shopping and bookings (docs/commerce-contract.md). Everything here is SIMULATED: no real merchant,
// account, card or charge. The browser only prepares drafts, picks offers and reads receipts; approving a purchase is
// always the existing plans flow with the exact reviewed fingerprint (lib/integrations approvePlan), and money is
// never "remembered". Money is integer paise everywhere; it is formatted for people only at the edge.
import { call, defaultHttp, IntegrationError, parsePlan, type Http, type Plan } from "./integrations";

export const DOMAINS = ["retail", "tickets", "dining"] as const;
export type Domain = typeof DOMAINS[number];
export const TRANSACTION_STATUSES = ["collecting", "choosing", "quoted", "awaiting-approval", "executing", "completed", "unknown", "cancelled", "expired"] as const;
export type TransactionStatus = typeof TRANSACTION_STATUSES[number];
export const SEAT_STATUSES = ["free", "taken", "blocked", "accessible", "selected"] as const;
export type SeatStatus = typeof SEAT_STATUSES[number];

export type Seat = { id: string; label: string; status: SeatStatus };
/** Rows run from the screen (first) to the back (last). `gapsAfter`: seat indexes followed by an aisle. */
export type SeatRow = { label: string; seats: Seat[]; gapsAfter?: number[] };
export type SeatMap = { screen: "top"; rows: SeatRow[] };
export type Offer = { id: string; title: string; merchant: string; description: string; totalMinor: number; currency: "INR"; available: boolean; seats?: string[]; seatMap?: SeatMap };
export type QuoteLine = { label: string; quantity: number; unitMinor: number; totalMinor: number };
export type Quote = { id: string; revision: number; fingerprint: string; merchant: string; currency: "INR"; totalMinor: number; lines: QuoteLine[]; terms: string;
  expiresAt: number; selection: Record<string, string | number | string[]>; summary: string };
export type Receipt = { id: string; transactionId: string; status: "confirmed" | "cancelled"; simulated: true; totalMinor: number; currency: "INR"; createdAt: number; detail: string };
export type Transaction = { id: string; conversationId: string; domain: Domain; status: TransactionStatus; simulated: true; slots: Record<string, string | number>;
  missing: string[]; offers: Offer[]; quote: Quote | null; planId: string | null; receipt: Receipt | null; lastReply: string };
export type TransactionsState = { serverNow: number; transactions: Transaction[]; preferences: Record<string, string> };
export type RespondReply = { serverNow: number; reply: string; transaction: Transaction | null; plan: Plan | null };

const ID = /^[A-Za-z0-9_-]{1,80}$/;
const invalid = () => new IntegrationError("June returned a booking in an unexpected form.", 502, "invalid-response");
const obj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const str = (v: unknown, max: number, empty = true): v is string => typeof v === "string" && v.length <= max && (empty || v.trim().length > 0);
const minor = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) >= 0 && (v as number) <= 1e10;  // integer paise only
const time = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v > 0;

function parseSeatMap(v: unknown): SeatMap {
  if (!obj(v) || v.screen !== "top" || !Array.isArray(v.rows) || v.rows.length < 1 || v.rows.length > 40) throw invalid();
  const ids = new Set<string>();
  return { screen: "top", rows: v.rows.map(r => {
    if (!obj(r) || !str(r.label, 4, false) || !Array.isArray(r.seats) || r.seats.length < 1 || r.seats.length > 60) throw invalid();
    const seats = r.seats.map(s => {
      if (!obj(s) || typeof s.id !== "string" || !ID.test(s.id) || ids.has(s.id) || !str(s.label, 8, false) || !SEAT_STATUSES.includes(s.status as SeatStatus)) throw invalid();
      ids.add(s.id);
      return { id: s.id, label: s.label, status: s.status as SeatStatus };
    });
    const gaps = r.gapsAfter === undefined ? undefined : r.gapsAfter;
    if (gaps !== undefined && (!Array.isArray(gaps) || gaps.length > 10 || !gaps.every(g => Number.isInteger(g) && g >= 0 && g < seats.length - 1))) throw invalid();
    return { label: r.label, seats, ...(gaps ? { gapsAfter: [...gaps] as number[] } : {}) };
  }) };
}

function parseOffer(v: unknown): Offer {
  if (!obj(v) || typeof v.id !== "string" || !ID.test(v.id) || !str(v.title, 160, false) || !str(v.merchant, 80, false) || !str(v.description, 400)
    || !minor(v.totalMinor) || v.currency !== "INR" || typeof v.available !== "boolean") throw invalid();
  if (v.seats !== undefined && (!Array.isArray(v.seats) || v.seats.length > 20 || !v.seats.every(s => typeof s === "string" && ID.test(s)))) throw invalid();
  return { id: v.id, title: v.title, merchant: v.merchant, description: v.description, totalMinor: v.totalMinor, currency: "INR", available: v.available,
    ...(v.seats ? { seats: [...v.seats] as string[] } : {}), ...(v.seatMap !== undefined ? { seatMap: parseSeatMap(v.seatMap) } : {}) };
}

function parseQuote(v: unknown): Quote {
  if (!obj(v) || typeof v.id !== "string" || !ID.test(v.id) || !Number.isInteger(v.revision) || (v.revision as number) < 1 || typeof v.fingerprint !== "string"
    || !/^[A-Za-z0-9_-]{8,128}$/.test(v.fingerprint) || !str(v.merchant, 80, false) || v.currency !== "INR" || !minor(v.totalMinor)
    || !Array.isArray(v.lines) || v.lines.length < 1 || v.lines.length > 30 || !str(v.terms, 1200) || !time(v.expiresAt) || !obj(v.selection) || !str(v.summary, 1500, false)) throw invalid();
  const lines = v.lines.map(l => {
    if (!obj(l) || !str(l.label, 160, false) || !Number.isInteger(l.quantity) || (l.quantity as number) < 1 || (l.quantity as number) > 99 || !minor(l.unitMinor) || !minor(l.totalMinor)) throw invalid();
    return { label: l.label, quantity: l.quantity as number, unitMinor: l.unitMinor, totalMinor: l.totalMinor };
  });
  // The shown total must be exactly the sum of its lines: a mismatch is a malformed quote, never something to display.
  if (lines.reduce((sum, l) => sum + l.totalMinor, 0) !== v.totalMinor) throw invalid();
  const selection: Quote["selection"] = {};
  for (const [k, value] of Object.entries(v.selection)) {
    if (!ID.test(k) || !(str(value, 200) || (typeof value === "number" && Number.isFinite(value)) || (Array.isArray(value) && value.length <= 20 && value.every(x => str(x, 80))))) throw invalid();
    selection[k] = Array.isArray(value) ? [...value] as string[] : value as string | number;
  }
  return { id: v.id, revision: v.revision as number, fingerprint: v.fingerprint, merchant: v.merchant, currency: "INR", totalMinor: v.totalMinor, lines,
    terms: v.terms, expiresAt: v.expiresAt, selection, summary: v.summary };
}

function parseReceipt(v: unknown): Receipt {
  if (!obj(v) || typeof v.id !== "string" || !ID.test(v.id) || typeof v.transactionId !== "string" || !ID.test(v.transactionId)
    || (v.status !== "confirmed" && v.status !== "cancelled") || v.simulated !== true || !minor(v.totalMinor) || v.currency !== "INR" || !time(v.createdAt) || !str(v.detail, 600)) throw invalid();
  return { id: v.id, transactionId: v.transactionId, status: v.status, simulated: true, totalMinor: v.totalMinor, currency: "INR", createdAt: v.createdAt, detail: v.detail };
}

export function parseTransaction(v: unknown): Transaction {
  if (!obj(v) || typeof v.id !== "string" || !ID.test(v.id) || typeof v.conversationId !== "string" || !/^[A-Za-z0-9_-]{1,120}$/.test(v.conversationId)
    || !DOMAINS.includes(v.domain as Domain) || !TRANSACTION_STATUSES.includes(v.status as TransactionStatus) || v.simulated !== true
    || !obj(v.slots) || !Array.isArray(v.missing) || v.missing.length > 12 || !v.missing.every(m => str(m, 40, false))
    || !Array.isArray(v.offers) || v.offers.length > 12 || !(v.planId === null || (typeof v.planId === "string" && /^[a-f0-9]{32}$/.test(v.planId)))
    || !str(v.lastReply, 2000)) throw invalid();
  const slots: Transaction["slots"] = {};
  for (const [k, value] of Object.entries(v.slots)) {
    if (!ID.test(k) || !(str(value, 200) || (typeof value === "number" && Number.isFinite(value)))) throw invalid();
    slots[k] = value as string | number;
  }
  const transaction: Transaction = { id: v.id, conversationId: v.conversationId, domain: v.domain as Domain, status: v.status as TransactionStatus, simulated: true,
    slots, missing: [...v.missing] as string[], offers: v.offers.map(parseOffer), quote: v.quote === null ? null : parseQuote(v.quote),
    planId: v.planId as string | null, receipt: v.receipt === null ? null : parseReceipt(v.receipt), lastReply: v.lastReply };
  // A dining reservation never charges: a non-zero dining amount is a contract violation, not something to show.
  if (transaction.domain === "dining" && ((transaction.quote?.totalMinor ?? 0) !== 0 || (transaction.receipt?.totalMinor ?? 0) !== 0)) throw invalid();
  if (transaction.receipt && transaction.receipt.transactionId !== transaction.id) throw invalid();
  return transaction;
}

/** ₹1,240 / ₹1,240.50 from integer paise (Indian digit grouping). */
export function rupees(totalMinor: number) {
  if (!Number.isSafeInteger(totalMinor) || totalMinor < 0) return "";
  const whole = totalMinor % 100 === 0;
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2 }).format(totalMinor / 100);
}

export const STATUS_WORDS: Record<TransactionStatus, string> = {
  collecting: "Getting details", choosing: "Choosing", quoted: "Quote ready", "awaiting-approval": "Waiting for your approval", executing: "Booking (simulated)…",
  completed: "Done (simulated)", unknown: "Outcome not confirmed · check before asking again", cancelled: "Cancelled", expired: "Quote expired · ask for a fresh one",
};
export const DOMAIN_WORDS: Record<Domain, string> = { retail: "Shopping", tickets: "Tickets", dining: "Table reservation" };

export async function getTransactions(http: Http = defaultHttp): Promise<TransactionsState> {
  const data = await call(http, "/api/transactions");
  if (!Array.isArray(data.transactions) || data.transactions.length > 50 || !obj(data.preferences)) throw invalid();
  const preferences: Record<string, string> = {};
  for (const [k, v] of Object.entries(data.preferences)) { if (!ID.test(k) || !str(v, 200)) throw invalid(); preferences[k] = v as string; }
  return { serverNow: data.serverNow as number, transactions: data.transactions.map(parseTransaction), preferences };
}

export async function getTransaction(id: string, http: Http = defaultHttp) {
  if (!ID.test(id)) throw new IntegrationError("Choose a booking from June’s list.", 400, "invalid-input");
  const data = await call(http, `/api/transactions/${id}`);
  return { serverNow: data.serverNow as number, transaction: parseTransaction(data.transaction) };
}

/** Prepare or update a draft (free text, or a tapped offer). Never approves: approval is the plan card / voice approval. */
export async function respond(input: { conversationId: string; text?: string; select?: { offerId: string } }, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  const text = input.text?.trim();
  if (!/^[A-Za-z0-9_-]{1,120}$/.test(input.conversationId) || (!text && !input.select) || (text !== undefined && (text.length > 2000 || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(text)))
    || (input.select && !ID.test(input.select.offerId))) throw new IntegrationError("June could not send that to the booking.", 400, "invalid-input");
  const body = { requestId: uuid(), conversationId: input.conversationId, ...(text ? { text } : {}), ...(input.select ? { select: { offerId: input.select.offerId } } : {}) };
  const data = await call(http, "/api/transactions/respond", body);
  if (!str(data.reply, 2000)) throw invalid();
  const plan = data.plan === undefined || data.plan === null ? null : parsePlan(data.plan);
  if (data.plan != null && !plan) throw invalid();
  return { serverNow: data.serverNow as number, reply: data.reply as string, transaction: data.transaction == null ? null : parseTransaction(data.transaction), plan } satisfies RespondReply;
}

/** A stable temporary-session id for actions started in the Systems panel, so they never write normal chat history. */
export function panelSession(storage: Pick<Storage, "getItem" | "setItem"> | null) {
  const make = () => "panel-" + crypto.randomUUID().replace(/-/g, "");
  try {
    const saved = storage?.getItem("june-transactions-session");
    if (saved && /^panel-[a-f0-9]{32}$/.test(saved)) return saved;
    const fresh = make(); storage?.setItem("june-transactions-session", fresh); return fresh;
  } catch { return make(); }
}
