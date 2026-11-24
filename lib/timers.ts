// Local timers. The server owns time and completion; the browser only shows a
// countdown on the server's clock and never decides that a timer has finished.

export const TIMER_STATUSES = ["active", "completed", "cancelled", "acknowledged"] as const;
export type TimerStatus = typeof TIMER_STATUSES[number];
export type Timer = { id: string; label: string; durationSeconds: number; createdAt: number; endsAt: number; status: TimerStatus; completedAt?: number };
export type TimerState = { serverNow: number; timers: Timer[] };
type Http = (url: string, init?: RequestInit) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

const ID = /^[\w-]{8,128}$/;
const time = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0;
const validDuration = (value: unknown) => Number.isInteger(value) && (value as number) >= 1 && (value as number) <= 86400;

export function parseTimer(value: unknown): Timer | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  if (typeof v.id !== "string" || !ID.test(v.id) || !TIMER_STATUSES.includes(v.status as TimerStatus)) return null;
  if (typeof v.label !== "string" || v.label.length > 80 || !validDuration(v.durationSeconds) || !time(v.createdAt) || !time(v.endsAt)) return null;
  return { id: v.id, label: v.label, durationSeconds: v.durationSeconds as number, createdAt: v.createdAt as number, endsAt: v.endsAt as number,
    status: v.status as TimerStatus, ...(time(v.completedAt) ? { completedAt: v.completedAt as number } : {}) };
}
export function parseTimers(value: unknown): TimerState | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (!time(v.serverNow) || !Array.isArray(v.timers)) return null;
  return { serverNow: v.serverNow as number, timers: v.timers.map(parseTimer).filter((t): t is Timer => t !== null) };
}

/** Time left on the server's deadline, advanced by local time since the server replied. */
export function remainingMs(timer: Timer, serverNow: number, receivedAt: number, now: number) {
  return timer.endsAt - (serverNow + Math.max(0, now - receivedAt));
}
/** m:ss or h:mm:ss, rounded up so a running timer never shows 0:00 early. */
export function formatClock(ms: number) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}
/** Only the server's status ends a timer; at 0:00 the UI waits for it. */
export function timerText(timer: Timer, remaining: number) {
  if (timer.status === "completed") return "Done";
  if (timer.status === "cancelled") return "Cancelled";
  if (timer.status === "acknowledged") return "Dismissed";
  return remaining > 0 ? formatClock(remaining) : "Finishing…";
}
export function durationWords(seconds: number) {
  if (seconds % 3600 === 0) return `${seconds / 3600}-hour`;
  if (seconds % 60 === 0) return `${seconds / 60}-minute`;
  if (seconds < 60) return `${seconds}-second`;
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  return [h && `${h} hour`, m && `${m} minute`, s && `${s} second`].filter(Boolean).join(" ");
}
/** The one fixed sentence June speaks for a finished timer. */
export function timerPhrase(timer: Timer) {
  return `Your ${timer.label.trim() || durationWords(timer.durationSeconds)} timer is done.`;
}

// active → completed or cancelled → acknowledged. A late reply never moves a timer back.
const RANK: Record<TimerStatus, number> = { active: 0, completed: 1, cancelled: 1, acknowledged: 2 };
export function mergeTimer(current: Timer | undefined, incoming: Timer) {
  if (!current || current.id !== incoming.id) return incoming;
  if (RANK[current.status] > RANK[incoming.status] || (RANK[current.status] === RANK[incoming.status] && current.status !== incoming.status)) return current;
  return incoming;
}
export function mergeTimers(current: readonly Timer[], incoming: readonly Timer[]) {
  const known = new Map(current.map(t => [t.id, t]));
  const merged = incoming.map(t => mergeTimer(known.get(t.id), t));
  const seen = new Set(merged.map(t => t.id));
  return [...merged, ...current.filter(t => !seen.has(t.id))];
}

async function call(http: Http, url: string, body?: unknown) {
  const response = await http(url, body === undefined ? { cache: "no-store" } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
  const data = await response.json().catch(() => null) as Record<string, unknown> | null;
  if (!response.ok) throw new Error(typeof data?.message === "string" ? data.message : "June could not reach Timers. Try again.");
  return data;
}
function timerReply(data: Record<string, unknown> | null, id?: string) {
  const timer = parseTimer(data?.timer);
  if (!timer || !time(data?.serverNow) || (id && timer.id !== id)) throw new Error("June returned an unexpected timer.");
  return { serverNow: data!.serverNow as number, timer, announce: data?.announce === true };
}

const defaultHttp: Http = (url, init) => fetch(url, init);
export async function getTimers(http: Http = defaultHttp) {
  const state = parseTimers(await call(http, "/api/timers"));
  if (!state) throw new Error("June returned unexpected timers.");
  return state;
}
/** Idempotent on requestId: one retry after a dropped connection reuses it, so a timer is never made twice. */
export async function createTimer(input: { durationSeconds: number; label?: string }, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  if (!validDuration(input.durationSeconds)) throw new Error("A timer runs between 1 second and 24 hours.");
  const label = (input.label ?? "").trim();
  if (label.length > 80) throw new Error("Keep the timer name to 80 characters.");
  const body = { durationSeconds: input.durationSeconds, ...(label ? { label } : {}), requestId: uuid() };
  for (let attempt = 0; ; attempt++) {
    try { return timerReply(await call(http, "/api/timers", body)); }
    catch (failure) {
      if (!(failure instanceof TypeError)) throw failure;
      if (attempt) throw new Error("June could not confirm the timer was set. Check Timers before trying again.");
    }
  }
}
const decide = (kind: "cancel" | "acknowledge" | "claim") => async (timer: Timer, http: Http = defaultHttp) =>
  timerReply(await call(http, `/api/timers/${encodeURIComponent(timer.id)}/${kind}`, {}), timer.id);
export const cancelTimer = decide("cancel");
export const acknowledgeTimer = decide("acknowledge");
/** At most once across tabs: only a reply with announce:true may be spoken. */
export const claimTimer = decide("claim");
