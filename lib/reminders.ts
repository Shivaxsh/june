// Local reminders. The server owns the clock, the zone conversion and completion;
// the browser shows due times in the reminder's own zone and never completes one.

export const REMINDER_STATUSES = ["active", "completed", "cancelled", "acknowledged"] as const;
export type ReminderStatus = typeof REMINDER_STATUSES[number];
/** `revision` rises by one on every edit or snooze; each revision is its own occurrence. */
export const OUTCOMES = ["missed", "skipped", "paused"] as const;
export type ReminderOutcome = typeof OUTCOMES[number];
/**
 * `revision` rises by one on every edit or snooze; each revision is its own occurrence.
 * A repeating reminder's occurrences add `seriesId` and `occurrenceDate` (its local day), and resolved ones an `outcome`.
 */
export type Reminder = { id: string; text: string; dueAt: number; timeZone: string; createdAt: number; status: ReminderStatus; revision: number; completedAt?: number; announcedAt?: number;
  seriesId?: string; occurrenceDate?: string; outcome?: ReminderOutcome; dstAdjusted?: boolean };
/** A repeating reminder. Only due occurrences exist as reminders; the next one is described by `nextScheduledAt`. */
export type Series = { id: string; text: string; rule: "daily" | "weekly"; weekdays: number[]; localTime: string; timeZone: string; startDate: string;
  status: "active" | "paused" | "cancelled"; revision: number; createdAt: number; nextScheduledAt: number | null; nextOccurrenceDate: string | null;
  lastMissed: { occurrenceDate: string; count: number; at: number } | null };
export type ReminderState = { serverNow: number; timeZone: string; reminders: Reminder[]; series: Series[] };
type Http = (url: string, init?: RequestInit) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

export const DEFAULT_TIME_ZONE = "Asia/Kolkata";
const ID = /^[\w-]{8,128}$/;
const ZONE = /^[A-Za-z][\w+-]*(?:\/[\w+-]+){0,2}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const CLOCK = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const time = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0;
/** A real IANA zone: shaped like one and accepted by Intl. */
const zone = (value: unknown) => {
  if (typeof value !== "string" || value.length > 64 || !ZONE.test(value)) return false;
  try { new Intl.DateTimeFormat("en", { timeZone: value }); return true; } catch { return false; }
};
/** Characters as people count them (code points), so 200 emoji are 200, not 400 UTF-16 units. */
const characters = (text: string) => Array.from(text).length;

export function parseReminder(value: unknown): Reminder | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  if (typeof v.id !== "string" || !ID.test(v.id) || !REMINDER_STATUSES.includes(v.status as ReminderStatus)) return null;
  if (typeof v.text !== "string" || !v.text.trim() || characters(v.text) > 200 || !time(v.dueAt) || !time(v.createdAt) || !zone(v.timeZone)) return null;
  // Legacy records have no revision: they are revision 1.
  const revision = v.revision === undefined ? 1 : v.revision;
  if (!Number.isInteger(revision) || (revision as number) < 1) return null;
  // Series fields are optional (one-shot reminders have none) but strictly typed when present.
  if (v.seriesId !== undefined && (typeof v.seriesId !== "string" || !ID.test(v.seriesId))) return null;
  if (v.occurrenceDate !== undefined && (typeof v.occurrenceDate !== "string" || !DATE.test(v.occurrenceDate))) return null;
  if (v.outcome !== undefined && !OUTCOMES.includes(v.outcome as ReminderOutcome)) return null;
  if (v.dstAdjusted !== undefined && typeof v.dstAdjusted !== "boolean") return null;
  return { id: v.id, text: v.text, dueAt: v.dueAt as number, timeZone: v.timeZone as string, createdAt: v.createdAt as number, status: v.status as ReminderStatus, revision: revision as number,
    ...(time(v.completedAt) ? { completedAt: v.completedAt as number } : {}), ...(time(v.announcedAt) ? { announcedAt: v.announcedAt as number } : {}),
    ...(v.seriesId === undefined ? {} : { seriesId: v.seriesId as string }), ...(v.occurrenceDate === undefined ? {} : { occurrenceDate: v.occurrenceDate as string }),
    ...(v.outcome === undefined ? {} : { outcome: v.outcome as ReminderOutcome }), ...(v.dstAdjusted === undefined ? {} : { dstAdjusted: v.dstAdjusted as boolean }) };
}
export function parseReminders(value: unknown): ReminderState | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (!time(v.serverNow) || !Array.isArray(v.reminders)) return null;
  return { serverNow: v.serverNow as number, timeZone: zone(v.timeZone) ? v.timeZone as string : DEFAULT_TIME_ZONE,
    reminders: v.reminders.map(parseReminder).filter((r): r is Reminder => r !== null),
    series: Array.isArray(v.series) ? v.series.map(parseSeries).filter((x): x is Series => x !== null) : [] };
}

/** YYYY-MM-DD for an instant in a zone (the date the person means by "today" there). */
export function localDate(ms: number, timeZone: string) {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(ms));
}
/**
 * The next whole hour in that zone, as a date and a time together, so 23:45 becomes tomorrow 00:00
 * rather than a past "today 00:00". Uses the zone's own minutes, so half-hour offsets (IST) are exact.
 */
export function nextHourDefault(ms: number, timeZone: string) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone, minute: "2-digit", second: "2-digit" }).formatToParts(new Date(ms)).map(p => [p.type, p.value]));
  const next = ms - (ms % 1000) + ((60 - Number(parts.minute)) * 60 - Number(parts.second)) * 1000;
  const hour = new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", hourCycle: "h23" }).format(new Date(next));
  return { date: localDate(next, timeZone), time: `${hour}:00` };
}
/** HH:MM for an instant in a zone (prefills the Edit time field). */
export function localClock(ms: number, timeZone: string) {
  return new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(ms));
}
const dayNumber = (date: string) => { const [y, m, d] = date.split("-").map(Number); return Date.UTC(y, m - 1, d) / 86400_000; };
/** "Today, 6:00 pm", "Tomorrow, 9:30 am" or "Mon 16 Nov, 12:00 pm", in the reminder's zone and relative to the server's today. */
export function formatDue(dueAt: number, timeZone: string, serverNow: number) {
  const clock = new Intl.DateTimeFormat("en-US", { timeZone, hour: "numeric", minute: "2-digit", hour12: true }).format(new Date(dueAt)).toLowerCase();
  const days = dayNumber(localDate(dueAt, timeZone)) - dayNumber(localDate(serverNow, timeZone));
  const day = days === 0 ? "Today" : days === 1 ? "Tomorrow" : days === -1 ? "Yesterday"
    : new Intl.DateTimeFormat("en-GB", { timeZone, weekday: "short", day: "numeric", month: "short" }).format(new Date(dueAt)).replace(",", "");
  return `${day}, ${clock}`;
}
/** The one fixed sentence June speaks for a due reminder. */
export function reminderPhrase(reminder: Reminder) {
  const text = reminder.text.trim();
  return `Reminder: ${text}${/[.!?]$/.test(text) ? "" : "."}`;
}

const RANK: Record<ReminderStatus, number> = { active: 0, completed: 1, cancelled: 1, acknowledged: 2 };
/** The alert-queue key: each revision is its own occurrence, claimed and spoken at most once. */
export const reminderKey = (reminder: Reminder) => `reminder:${reminder.id}:${reminder.revision}`;

/** A newer revision always wins (an edit or snooze makes a due reminder active again); otherwise statuses only move forward. */
export function mergeReminder(current: Reminder | undefined, incoming: Reminder) {
  if (!current || current.id !== incoming.id) return incoming;
  if (incoming.revision !== current.revision) return incoming.revision > current.revision ? incoming : current;
  if (RANK[current.status] > RANK[incoming.status] || (RANK[current.status] === RANK[incoming.status] && current.status !== incoming.status)) return current;
  return incoming;
}
export function mergeReminders(current: readonly Reminder[], incoming: readonly Reminder[]) {
  const known = new Map(current.map(r => [r.id, r]));
  const merged = incoming.map(r => mergeReminder(known.get(r.id), r));
  const seen = new Set(merged.map(r => r.id));
  return [...merged, ...current.filter(r => !seen.has(r.id))];
}
/** Next status check: just after the nearest due time (1 s to 60 s), or none when nothing is active. */
export function nextReminderCheck(reminders: readonly Reminder[], serverNow: number, receivedAt: number, now: number) {
  const active = reminders.filter(r => r.status === "active");
  if (!active.length) return null;
  const until = Math.min(...active.map(r => r.dueAt)) - (serverNow + Math.max(0, now - receivedAt));
  return until <= 0 ? 1000 : Math.min(60_000, Math.max(1000, until + 750));
}

/** A refused request, with its HTTP status (409: the reminder changed somewhere else). */
export class ReminderError extends Error { constructor(message: string, readonly status: number) { super(message); } }
export const isConflict = (error: unknown) => error instanceof ReminderError && error.status === 409;

async function call(http: Http, url: string, body?: unknown) {
  const response = await http(url, body === undefined ? { cache: "no-store" } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
  const data = await response.json().catch(() => null) as Record<string, unknown> | null;
  if (!response.ok) throw new ReminderError(typeof data?.message === "string" ? data.message : "June could not reach Reminders. Try again.", response.status);
  return data;
}
function reminderReply(data: Record<string, unknown> | null, id?: string) {
  const reminder = parseReminder(data?.reminder);
  if (!reminder || !time(data?.serverNow) || (id && reminder.id !== id)) throw new Error("June returned an unexpected reminder.");
  return { serverNow: data!.serverNow as number, reminder, announce: data?.announce === true };
}
const defaultHttp: Http = (url, init) => fetch(url, init);
export async function getReminders(http: Http = defaultHttp) {
  const state = parseReminders(await call(http, "/api/reminders"));
  if (!state) throw new Error("June returned unexpected reminders.");
  return state;
}
/** Shape checks only; the server owns zones, past times, the 30-day limit and the 20-reminder cap. */
export async function createReminder(input: { text: string; localDate: string; localTime: string; timeZone?: string }, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  const text = checkText(input.text);
  checkWhen(input.localDate, input.localTime);
  const body = { text, localDate: input.localDate, localTime: input.localTime, ...(input.timeZone ? { timeZone: input.timeZone } : {}), requestId: uuid() };
  return once(() => call(http, "/api/reminders", body), undefined);
}
function checkText(raw: string) {
  const text = raw.trim();
  if (!text) throw new Error("Say what to remind you about.");
  if (characters(text) > 200) throw new Error("Keep a reminder to 200 characters.");
  return text;
}
function checkWhen(localDate: string, localTime: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(localDate)) throw new Error("Choose a date (YYYY-MM-DD).");
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(localTime)) throw new Error("Choose a time (HH:MM).");
}
/** One attempt, plus one retry with the same body (same requestId) after a dropped connection. */
async function once(send: () => Promise<Record<string, unknown> | null>, id: string | undefined) {
  for (let attempt = 0; ; attempt++) {
    try { return reminderReply(await send(), id); }
    catch (failure) {
      if (!(failure instanceof TypeError)) throw failure;
      if (attempt) throw new Error("June could not confirm the change was saved. Check Reminders before trying again.");
    }
  }
}
/** Move a reminder (and optionally reword it). Bound to the revision shown; a stale one gets 409. */
export async function rescheduleReminder(reminder: Reminder, input: { localDate: string; localTime: string; timeZone?: string; text?: string }, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  checkWhen(input.localDate, input.localTime);
  const text = input.text === undefined ? undefined : checkText(input.text);
  const body = { revision: reminder.revision, requestId: uuid(), localDate: input.localDate, localTime: input.localTime, ...(input.timeZone ? { timeZone: input.timeZone } : {}), ...(text === undefined ? {} : { text }) };
  return once(() => call(http, `/api/reminders/${encodeURIComponent(reminder.id)}/reschedule`, body), reminder.id);
}
/** Snooze a due reminder by a number of seconds from now (server clock). */
export async function snoozeReminder(reminder: Reminder, seconds: number, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 86400) throw new Error("Snooze for between 1 second and 24 hours.");
  const body = { revision: reminder.revision, requestId: uuid(), seconds };
  return once(() => call(http, `/api/reminders/${encodeURIComponent(reminder.id)}/snooze`, body), reminder.id);
}
const decide = (kind: "cancel" | "acknowledge" | "claim") => async (reminder: Reminder, http: Http = defaultHttp) =>
  reminderReply(await call(http, `/api/reminders/${encodeURIComponent(reminder.id)}/${kind}`, { revision: reminder.revision }), reminder.id);
export const cancelReminder = decide("cancel");
export const acknowledgeReminder = decide("acknowledge");
/** At most once across tabs: only announce:true may be spoken. */
export const claimReminder = decide("claim");

// ---- Repeating reminders (series) ----
export function parseSeries(value: unknown): Series | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  if (typeof v.id !== "string" || !ID.test(v.id) || typeof v.text !== "string" || !v.text.trim() || characters(v.text) > 200) return null;
  if (v.rule !== "daily" && v.rule !== "weekly") return null;
  if (!Array.isArray(v.weekdays) || !v.weekdays.length || !v.weekdays.every(d => Number.isInteger(d) && d >= 1 && d <= 7) || new Set(v.weekdays).size !== v.weekdays.length) return null;
  if (typeof v.localTime !== "string" || !CLOCK.test(v.localTime) || typeof v.startDate !== "string" || !DATE.test(v.startDate) || !zone(v.timeZone)) return null;
  if (!["active", "paused", "cancelled"].includes(v.status as string) || !Number.isInteger(v.revision) || (v.revision as number) < 1 || !time(v.createdAt)) return null;
  if (v.nextScheduledAt !== null && !time(v.nextScheduledAt)) return null;
  if (v.nextOccurrenceDate !== null && (typeof v.nextOccurrenceDate !== "string" || !DATE.test(v.nextOccurrenceDate))) return null;
  let lastMissed: Series["lastMissed"] = null;
  if (v.lastMissed !== null && v.lastMissed !== undefined) {
    const m = v.lastMissed as Record<string, unknown>;
    if (typeof m !== "object" || typeof m.occurrenceDate !== "string" || !DATE.test(m.occurrenceDate) || !Number.isInteger(m.count) || (m.count as number) < 1 || !time(m.at)) return null;
    lastMissed = { occurrenceDate: m.occurrenceDate, count: m.count as number, at: m.at as number };
  }
  return { id: v.id, text: v.text, rule: v.rule, weekdays: [...(v.weekdays as number[])].sort((a, b) => a - b), localTime: v.localTime, timeZone: v.timeZone as string,
    startDate: v.startDate, status: v.status as Series["status"], revision: v.revision as number, createdAt: v.createdAt as number,
    nextScheduledAt: v.nextScheduledAt as number | null, nextOccurrenceDate: v.nextOccurrenceDate as string | null, lastMissed };
}
/**
 * A newer configuration revision always wins. The scheduler advances the next occurrence without a
 * revision bump, so at an equal revision the later schedule wins: a slow older snapshot never moves it back.
 */
export function mergeSeries(current: Series | undefined, incoming: Series) {
  if (!current || current.id !== incoming.id) return incoming;
  if (incoming.revision !== current.revision) return incoming.revision > current.revision ? incoming : current;
  return (incoming.nextScheduledAt ?? -1) >= (current.nextScheduledAt ?? -1) ? incoming : current;
}
export function mergeSeriesList(current: readonly Series[], incoming: readonly Series[]) {
  const known = new Map(current.map(x => [x.id, x]));
  const merged = incoming.map(x => mergeSeries(known.get(x.id), x));
  const seen = new Set(merged.map(x => x.id));
  return [...merged, ...current.filter(x => !seen.has(x.id))];
}
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
/** "Daily · 11:00 pm", "Weekdays · 7:30 am" or "Mon, Thu · 9:00 am". */
export function describeRule(series: Series) {
  const [h, m] = series.localTime.split(":").map(Number);
  const clock = `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
  const days = series.weekdays.join(",");
  const label = series.rule === "daily" || days === "1,2,3,4,5,6,7" ? "Daily" : days === "1,2,3,4,5" ? "Weekdays" : series.weekdays.map(d => DAY_NAMES[d - 1]).join(", ");
  return `${label} · ${clock}`;
}
/** Snooze lengths (minutes) that end strictly before the next regular deadline; all of them when there is none. */
export function snoozeOptionsBefore(minutes: readonly number[], serverNow: number, nextScheduledAt: number | null) {
  return nextScheduledAt === null ? [...minutes] : minutes.filter(m => serverNow + m * 60_000 < nextScheduledAt);
}
/** Reminders allowed to speak: one-shots, and occurrences of a series that exists and is active. Paused or cancelled series stay silent. */
export function alertableReminders(reminders: readonly Reminder[], series: readonly Series[]) {
  const active = new Set(series.filter(x => x.status === "active").map(x => x.id));
  return reminders.filter(r => !r.seriesId || active.has(r.seriesId));
}
function seriesReply(data: Record<string, unknown> | null, id?: string) {
  const series = parseSeries(data?.series);
  if (!series || !time(data?.serverNow) || (id && series.id !== id)) throw new Error("June returned an unexpected repeating reminder.");
  const reminder = data?.reminder === undefined || data?.reminder === null ? null : parseReminder(data.reminder);
  return { serverNow: data!.serverNow as number, series, reminder };
}
async function seriesOnce(send: () => Promise<Record<string, unknown> | null>, id: string | undefined) {
  for (let attempt = 0; ; attempt++) {
    try { return seriesReply(await send(), id); }
    catch (failure) {
      if (!(failure instanceof TypeError)) throw failure;
      if (attempt) throw new Error("June could not confirm the change was saved. Check Reminders before trying again.");
    }
  }
}
function checkRule(rule: string, weekdays?: readonly number[]) {
  if (rule !== "daily" && rule !== "weekly") throw new Error("Choose Daily or Weekly.");
  if (rule === "weekly" && (!weekdays?.length || !weekdays.every(d => Number.isInteger(d) && d >= 1 && d <= 7))) throw new Error("Choose at least one day of the week.");
}
/** Start a repeating reminder. The server owns zones, the 30-day start window and the shared 20-reminder limit. */
export async function createSeries(input: { text: string; rule: "daily" | "weekly"; weekdays?: number[]; localTime: string; startDate: string; timeZone?: string }, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  const text = checkText(input.text);
  checkRule(input.rule, input.weekdays);
  checkWhen(input.startDate, input.localTime);
  const body = { text, rule: input.rule, ...(input.rule === "weekly" ? { weekdays: [...new Set(input.weekdays)].sort((a, b) => a - b) } : {}),
    localTime: input.localTime, startDate: input.startDate, ...(input.timeZone ? { timeZone: input.timeZone } : {}), requestId: uuid() };
  return seriesOnce(() => call(http, "/api/reminders/series", body), undefined);
}
/** Change the whole series (an already-due occurrence keeps its own text and time). Bound to the revision shown. */
export async function updateSeries(series: Series, changes: { text?: string; rule?: "daily" | "weekly"; weekdays?: number[]; localTime?: string; timeZone?: string }, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  const text = changes.text === undefined ? undefined : checkText(changes.text);
  if (changes.rule !== undefined) checkRule(changes.rule, changes.weekdays ?? series.weekdays);
  if (changes.localTime !== undefined && !CLOCK.test(changes.localTime)) throw new Error("Choose a time (HH:MM).");
  const body = { revision: series.revision, requestId: uuid(), ...(text === undefined ? {} : { text }), ...(changes.rule ? { rule: changes.rule } : {}),
    ...(changes.weekdays ? { weekdays: [...new Set(changes.weekdays)].sort((a, b) => a - b) } : {}), ...(changes.localTime ? { localTime: changes.localTime } : {}), ...(changes.timeZone ? { timeZone: changes.timeZone } : {}) };
  return seriesOnce(() => call(http, `/api/reminders/series/${encodeURIComponent(series.id)}/update`, body), series.id);
}
const seriesAction = (kind: "pause" | "resume" | "cancel") => (series: Series, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) => {
  const body = { revision: series.revision, requestId: uuid() };
  return seriesOnce(() => call(http, `/api/reminders/series/${encodeURIComponent(series.id)}/${kind}`, body), series.id);
};
export const pauseSeries = seriesAction("pause");
export const resumeSeries = seriesAction("resume");
export const cancelSeries = seriesAction("cancel");
/** Skip the next scheduled day: bound to the revision and the date shown, so a stale click can never skip a newer slot. */
export async function skipNextSeries(series: Series, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  if (!series.nextOccurrenceDate) throw new Error("There is nothing scheduled to skip.");
  const body = { revision: series.revision, requestId: uuid(), occurrenceDate: series.nextOccurrenceDate };
  return seriesOnce(() => call(http, `/api/reminders/series/${encodeURIComponent(series.id)}/skip-next`, body), series.id);
}
/** Skip this one due (or snoozed) occurrence of a repeating reminder. */
export async function skipReminder(reminder: Reminder, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  const body = { revision: reminder.revision, requestId: uuid() };
  return once(() => call(http, `/api/reminders/${encodeURIComponent(reminder.id)}/skip`, body), reminder.id);
}
