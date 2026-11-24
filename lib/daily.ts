// June's daily assistant: settings, per-service consent, weather place, goals, Google
// Calendar (read-only), Apple Music playlist and an on-request briefing. Every value
// the server sends is checked strictly; facts in a briefing are app-built, never generated.

import { call, defaultHttp, idempotent, IntegrationError, list, parseConnection, type Connection, type Http } from "./integrations";

export const SECTION_KINDS = ["weather", "calendar", "goals"] as const;
export type SectionKind = typeof SECTION_KINDS[number];
export const SECTION_STATUSES = ["ok", "not-configured", "unavailable", "error"] as const;
export type SectionStatus = typeof SECTION_STATUSES[number];
export type Units = "metric" | "imperial";

export type Place = { name: string; region: string; country: string; latitude: number; longitude: number; timeZone: string };
export type PlaceOption = Place & { id: string };
export type Playlist = { id: string; name: string };
export type AssistantSettings = {
  revision: number;
  weather: { place: Place | null; units: Units };
  music: { playlist: Playlist | null };
  briefing: { sections: SectionKind[] };
};
export type Goal = { id: string; text: string; status: "active" | "done"; revision: number; createdAt: number; doneAt: number | null };
export type BriefingItem = { text: string; at?: number; allDay?: boolean };
export type BriefingSection = { kind: SectionKind; status: SectionStatus; title: string; message?: string; items: BriefingItem[] };
export type Briefing = { id: string; generatedAt: number; sections: BriefingSection[]; spoken: string };

const ID = /^[\w.:-]{1,128}$/;
const TOKEN = /^[\w-]{8,128}$/;
const FORBIDDEN = ["command", "argv", "args", "shell", "cwd", "path", "script", "exec", "token", "accessToken", "refreshToken", "clientSecret"];
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown, max: number) => typeof v === "string" && v.trim().length > 0 && Array.from(v).length <= max;
const time = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v >= 0;
const clean = (v: Record<string, unknown>) => !FORBIDDEN.some(k => k in v);
const between = (v: unknown, lo: number, hi: number) => typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi;
const zone = (v: unknown) => { if (!text(v, 64)) return false; try { new Intl.DateTimeFormat("en", { timeZone: v as string }); return true; } catch { return false; } };
const invalid = () => new IntegrationError("June returned an unexpected daily-assistant reply.", 502, "invalid-reply");

export function parsePlace(v: unknown): Place | null {
  if (!object(v) || !clean(v) || !text(v.name, 120) || typeof v.region !== "string" || Array.from(v.region).length > 120 || !text(v.country, 80)) return null;
  if (!between(v.latitude, -90, 90) || !between(v.longitude, -180, 180) || !zone(v.timeZone)) return null;
  return { name: v.name as string, region: v.region, country: v.country as string, latitude: v.latitude as number, longitude: v.longitude as number, timeZone: v.timeZone as string };
}
export function parsePlaceOption(v: unknown): PlaceOption | null {
  const place = parsePlace(v);
  return place && object(v) && typeof v.id === "string" && ID.test(v.id) ? { ...place, id: v.id } : null;
}
export function parsePlaylist(v: unknown): Playlist | null {
  return object(v) && clean(v) && typeof v.id === "string" && ID.test(v.id) && text(v.name, 200) ? { id: v.id, name: v.name as string } : null;
}
export function parseSettings(v: unknown): AssistantSettings | null {
  if (!object(v) || !clean(v) || !Number.isInteger(v.revision) || (v.revision as number) < 1) return null;
  const w = v.weather, m = v.music, b = v.briefing;
  if (!object(w) || !object(m) || !object(b) || (w.units !== "metric" && w.units !== "imperial")) return null;
  const place = w.place === null ? null : parsePlace(w.place);
  const playlist = m.playlist === null ? null : parsePlaylist(m.playlist);
  if ((w.place !== null && !place) || (m.playlist !== null && !playlist)) return null;
  if (!Array.isArray(b.sections) || b.sections.length > 3 || !b.sections.every(s => SECTION_KINDS.includes(s)) || new Set(b.sections).size !== b.sections.length) return null;
  return { revision: v.revision as number, weather: { place, units: w.units }, music: { playlist }, briefing: { sections: [...b.sections] as SectionKind[] } };
}
export function parseGoal(v: unknown): Goal | null {
  if (!object(v) || !clean(v) || typeof v.id !== "string" || !TOKEN.test(v.id) || !text(v.text, 200)) return null;
  if ((v.status !== "active" && v.status !== "done") || !Number.isInteger(v.revision) || (v.revision as number) < 1 || !time(v.createdAt)) return null;
  if (v.doneAt !== null && !time(v.doneAt)) return null;
  if ((v.status === "done") !== (v.doneAt !== null)) return null;
  return { id: v.id, text: v.text as string, status: v.status, revision: v.revision as number, createdAt: v.createdAt as number, doneAt: v.doneAt as number | null };
}
function parseItem(v: unknown): BriefingItem | null {
  if (!object(v) || !clean(v) || !text(v.text, 300)) return null;
  if (v.at !== undefined && !time(v.at)) return null;
  if (v.allDay !== undefined && typeof v.allDay !== "boolean") return null;
  return { text: v.text as string, ...(v.at !== undefined ? { at: v.at as number } : {}), ...(v.allDay ? { allDay: true } : {}) };
}
function parseSection(v: unknown): BriefingSection | null {
  if (!object(v) || !clean(v) || !SECTION_KINDS.includes(v.kind as SectionKind) || !SECTION_STATUSES.includes(v.status as SectionStatus) || !text(v.title, 80)) return null;
  if (v.message !== undefined && !text(v.message, 300)) return null;
  if (!Array.isArray(v.items) || v.items.length > 20) return null;
  const items = v.items.map(parseItem);
  if (items.some(i => i === null)) return null;
  // A section that is not "ok" says why and carries no facts.
  if (v.status !== "ok" && (items.length || v.message === undefined)) return null;
  return { kind: v.kind as SectionKind, status: v.status as SectionStatus, title: v.title as string, ...(v.message !== undefined ? { message: v.message as string } : {}), items: items as BriefingItem[] };
}
export function parseBriefing(v: unknown): Briefing | null {
  if (!object(v) || !clean(v) || typeof v.id !== "string" || !TOKEN.test(v.id) || !time(v.generatedAt) || !text(v.spoken, 1200)) return null;
  if (!Array.isArray(v.sections) || v.sections.length < 1 || v.sections.length > 3) return null;
  const sections = v.sections.map(parseSection);
  if (sections.some(s => s === null) || new Set(sections.map(s => s!.kind)).size !== sections.length) return null;
  return { id: v.id, generatedAt: v.generatedAt as number, sections: sections as BriefingSection[], spoken: v.spoken as string };
}

function one<K extends string, T>(data: Record<string, unknown>, key: K, parse: (v: unknown) => T | null): { serverNow: number } & Record<K, T> {
  const value = parse(data[key]);
  if (!value) throw invalid();
  return { serverNow: data.serverNow as number, [key]: value } as { serverNow: number } & Record<K, T>;
}
const uuid = () => crypto.randomUUID();

export async function getSettings(http: Http = defaultHttp) {
  return one(await call(http, "/api/assistant/settings"), "settings", parseSettings);
}
export type SettingsChange = { weather?: { placeId: string } | { units: Units }; music?: { playlistId: string | null }; briefing?: { sections: SectionKind[] } };
export async function updateSettings(current: AssistantSettings, change: SettingsChange, http: Http = defaultHttp, id = uuid) {
  return one(await idempotent(http, "/api/assistant/settings", { requestId: id(), revision: current.revision, ...change }), "settings", parseSettings);
}

/** Turns one service's outbound access on or off. Enabling never happens without a click. */
export async function setConnection(id: "open-meteo" | "apple-music" | "apple-calendar", enabled: boolean, http: Http = defaultHttp, rid = uuid) {
  const reply = one(await idempotent(http, `/api/connections/${id}/${enabled ? "enable" : "disable"}`, { requestId: rid() }), "connection", parseConnection);
  if (reply.connection.id !== id) throw invalid();
  return reply;
}

export async function searchPlaces(query: string, http: Http = defaultHttp, id = uuid) {
  const q = query.trim();
  if (q.length < 2 || q.length > 80) throw new IntegrationError("Type a city name (2–80 characters).", 400, "invalid-query");
  const data = await idempotent(http, "/api/assistant/weather/places", { requestId: id(), query: q });
  return { serverNow: data.serverNow as number, places: list(data, "places", parsePlaceOption, 8) };
}

export async function getGoals(http: Http = defaultHttp) {
  const data = await call(http, "/api/assistant/goals");
  return { serverNow: data.serverNow as number, goals: list(data, "goals", parseGoal, 100) };
}
export async function addGoal(goalText: string, http: Http = defaultHttp, id = uuid) {
  const value = goalText.trim();
  if (!value || Array.from(value).length > 200) throw new IntegrationError("A goal needs 1 to 200 characters.", 400, "invalid-goal");
  return one(await idempotent(http, "/api/assistant/goals", { requestId: id(), text: value }), "goal", parseGoal);
}
export async function changeGoal(base: Goal, kind: "update" | "complete" | "reopen" | "delete", goalText?: string, http: Http = defaultHttp, id = uuid) {
  const body: Record<string, unknown> = { requestId: id(), revision: base.revision };
  if (kind === "update") {
    const value = (goalText ?? "").trim();
    if (!value || Array.from(value).length > 200) throw new IntegrationError("A goal needs 1 to 200 characters.", 400, "invalid-goal");
    body.text = value;
  }
  const data = await idempotent(http, `/api/assistant/goals/${encodeURIComponent(base.id)}/${kind}`, body);
  if (kind === "delete") { if (data.deleted !== true) throw invalid(); return { serverNow: data.serverNow as number, goal: null, deleted: true as const }; }
  const reply = one(data, "goal", parseGoal);
  if (reply.goal.id !== base.id) throw invalid();
  return { ...reply, deleted: false as const };
}

/**
 * Reads a downloaded Google "Desktop app" OAuth JSON in memory and returns only the
 * client id and secret. The file is never stored by the browser; the server keeps the
 * values in the macOS Keychain.
 */
export function readGoogleClient(json: string): { clientId: string; clientSecret: string } {
  let value: unknown;
  try { value = JSON.parse(json); } catch { throw new IntegrationError("That file is not valid JSON. Download the OAuth client JSON from Google Cloud again.", 400, "invalid-client"); }
  const installed = object(value) ? value.installed : undefined;
  if (!object(installed)) throw new IntegrationError("Choose the JSON for a Google OAuth client of type “Desktop app”.", 400, "invalid-client");
  const clientId = installed.client_id, clientSecret = installed.client_secret;
  if (typeof clientId !== "string" || !/^[\w-]{1,200}\.apps\.googleusercontent\.com$/.test(clientId) || typeof clientSecret !== "string" || !/^[\w-]{8,200}$/.test(clientSecret))
    throw new IntegrationError("The file does not contain a valid Desktop client id and secret.", 400, "invalid-client");
  return { clientId, clientSecret };
}
export async function configureGoogle(client: { clientId: string; clientSecret: string }, http: Http = defaultHttp, id = uuid) {
  return one(await idempotent(http, "/api/connections/google/configure", { requestId: id(), clientId: client.clientId, clientSecret: client.clientSecret }), "connection", parseConnection);
}
export const GOOGLE_SCOPES = ["calendar.events.readonly"] as const;
/** Starts consent; returns Google's URL, which the page opens only from the person's click. */
export async function authorizeGoogle(http: Http = defaultHttp, id = uuid) {
  const data = await idempotent(http, "/api/connections/google/authorize", { requestId: id(), scopes: [...GOOGLE_SCOPES] });
  const url = data.authUrl, expires = data.expiresAt;
  let parsed: URL | null = null;
  try { parsed = typeof url === "string" ? new URL(url) : null; } catch { parsed = null; }
  if (!parsed || parsed.protocol !== "https:" || parsed.hostname !== "accounts.google.com" || !time(expires)) throw invalid();
  return { serverNow: data.serverNow as number, authUrl: parsed.toString(), expiresAt: expires as number };
}
export async function revokeGoogle(http: Http = defaultHttp, id = uuid) {
  return one(await idempotent(http, "/api/connections/google/revoke", { requestId: id() }), "connection", parseConnection);
}

export async function getPlaylists(http: Http = defaultHttp) {
  const data = await call(http, "/api/assistant/music/playlists");
  return { serverNow: data.serverNow as number, playlists: list(data, "playlists", parsePlaylist, 500) };
}

export async function getBriefing(http: Http = defaultHttp, id = uuid) {
  return one(await idempotent(http, "/api/assistant/briefing", { requestId: id() }), "briefing", parseBriefing);
}

export type Today = { date: string; status: "ok" | "not-configured" | "unavailable"; items: string[] };
function parseToday(value: unknown): Today | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  if (Object.keys(v).some(k => !["date", "status", "items"].includes(k))) return null;
  if (typeof v.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v.date)) return null;
  if (v.status !== "ok" && v.status !== "not-configured" && v.status !== "unavailable") return null;
  if (!Array.isArray(v.items) || v.items.length > 20 || v.items.some(i => typeof i !== "string" || !i.trim() || i.length > 320)) return null;
  return { date: v.date, status: v.status, items: v.items as string[] };
}
/** Today's Calendar events, read from the Mac. Never prompts for permission. */
export async function getToday(http: Http = defaultHttp) {
  return one(await call(http, "/api/assistant/today"), "today", parseToday);
}
/** What June shows and says when the page opens on a day with events; null when there is nothing to say. */
export function todayPhrase(today: Today) {
  return today.status === "ok" && today.items.length ? "Today on your calendar: " + today.items.join(" ") : null;
}
/** Shown once per day and per set of events. */
export const todayKey = (today: Today) => today.date + "|" + today.items.join("|");

/** Times are shown in the chosen place's zone when known, otherwise this Mac's. */
export function itemTime(item: BriefingItem, timeZone?: string) {
  if (item.allDay) return "All day";
  if (item.at === undefined) return "";
  try { return new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit", ...(timeZone ? { timeZone } : {}) }).format(item.at); }
  catch { return new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit" }).format(item.at); }
}
/** The spoken line repeats the time ("18:00: Dentist."); beside a time label, show only the rest. */
export function itemText(item: BriefingItem) {
  if (item.at === undefined && !item.allDay) return item.text;
  const rest = item.text.replace(/^(?:All day|\d{1,2}:\d{2}):\s*/, "");
  return rest.trim() ? rest : item.text;
}
export const SECTION_WORDS: Record<SectionStatus, string> = { ok: "", "not-configured": "Not set up", unavailable: "Unavailable right now", error: "Could not load" };
