// June's integrations: what June can do (capabilities), which outside services are
// connected (connections), and multi-step plans the person reviews before anything runs.
// The browser never builds a command. It sends a requestId and an intent, and later
// the exact revision + fingerprint of the plan it showed. Every record is validated
// strictly; anything unexpected is refused rather than displayed.

export const VERSION = 1;
export const RISKS = ["read", "local", "outward", "financial"] as const;
export type Risk = typeof RISKS[number];
export const CONNECTION_STATES = ["not-configured", "needs-consent", "connected", "expired", "revoked", "error", "unsupported"] as const;
export type ConnectionState = typeof CONNECTION_STATES[number];
export const PLAN_STATUSES = ["proposed", "approved", "running", "completed", "partial", "failed", "cancelled", "expired", "unknown"] as const;
export type PlanStatus = typeof PLAN_STATUSES[number];
export const STEP_STATUSES = ["pending", "running", "completed", "failed", "skipped", "cancelled", "unknown"] as const;
export type StepStatus = typeof STEP_STATUSES[number];
export const INTENTS = ["open-vscode", "play-playlist", "focus-session", "open-app", "music-control", "music-library",
  "coding-session", "design-workspace", "keep-awake", "allow-sleep", "appearance", "convert-images",
  "project-pull", "project-push", "project-recipe", "project-command", "project-stop", "site-publish", "site-unpublish", "site-rollback", "job-apply"] as const;
export type Intent = typeof INTENTS[number];

export type Capability = { id: string; label: string; connector: string; risk: Risk; rememberable: boolean; available: boolean; unavailableReason?: string };
/** hosts: the exact destinations this connector would contact. enabled: whether the person allowed it (absent for connectors without a switch). */
export type Connection = { id: string; label: string; state: ConnectionState; hosts: string[]; scopes: string[]; checkedAt: number | null; message: string; enabled?: boolean };
export type StepResult = { message: string; verified: boolean; at: number };
/** Why a step did not run. "blocked-by-unknown": it never started because an earlier step's outcome is unconfirmed. */
export type StepReason = "blocked-by-unknown";
export type Step = { id: string; capability: string; label: string; preview: string; status: StepStatus; result?: StepResult; reason?: StepReason };
export type Plan = {
  id: string; revision: number; fingerprint: string; status: PlanStatus; title: string;
  createdAt: number; expiresAt: number; rememberable: boolean; steps: Step[];
  /** The person asked to stop a running plan: a step already running may finish; later steps will not start. */
  cancelRequested?: boolean;
};
export type Reply<T> = { serverNow: number } & T;

export type Http = (url: string, init?: RequestInit) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;
export const defaultHttp: Http = (url, init) => fetch(url, init);

const ID = /^[\w.:-]{1,128}$/;
const TOKEN = /^[\w-]{8,128}$/;
const HOST = /^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$/;
// A server record never carries anything executable; refuse one that tries, at any depth we read.
const FORBIDDEN = ["command", "argv", "args", "shell", "cwd", "path", "script", "exec"];
const MAX_STEPS = 12;

const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown, max: number) => typeof value === "string" && value.trim().length > 0 && Array.from(value).length <= max;
const time = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0;
const clean = (value: Record<string, unknown>) => !FORBIDDEN.some(key => key in value);
const strings = (value: unknown, test: (s: string) => boolean, max: number) =>
  Array.isArray(value) && value.length <= max && value.every(s => typeof s === "string" && test(s));

export function parseCapability(value: unknown): Capability | null {
  if (!object(value) || !clean(value)) return null;
  const v = value;
  if (typeof v.id !== "string" || !ID.test(v.id) || !text(v.label, 80) || typeof v.connector !== "string" || !ID.test(v.connector)) return null;
  if (!RISKS.includes(v.risk as Risk) || typeof v.rememberable !== "boolean" || typeof v.available !== "boolean") return null;
  // Sending, publishing and paying are never remembered, whatever a server claims.
  if (v.rememberable && (v.risk === "outward" || v.risk === "financial")) return null;
  if (!v.available && !text(v.unavailableReason, 300)) return null;
  return { id: v.id, label: v.label as string, connector: v.connector, risk: v.risk as Risk, rememberable: v.rememberable, available: v.available,
    ...(v.available ? {} : { unavailableReason: v.unavailableReason as string }) };
}

export function parseConnection(value: unknown): Connection | null {
  if (!object(value) || !clean(value)) return null;
  const v = value;
  if (typeof v.id !== "string" || !ID.test(v.id) || !text(v.label, 80) || !CONNECTION_STATES.includes(v.state as ConnectionState)) return null;
  if (!strings(v.hosts, h => HOST.test(h), 20) || !strings(v.scopes, s => text(s, 200), 30) || !text(v.message, 300)) return null;
  if (v.checkedAt !== null && !time(v.checkedAt)) return null;
  if (v.enabled !== undefined && typeof v.enabled !== "boolean") return null;
  // "Connected" is a verified fact: it needs a check time. Scopes exist only on a live connection.
  if (v.state === "connected" && v.checkedAt === null) return null;
  if (v.state !== "connected" && (v.scopes as string[]).length) return null;
  return { id: v.id, label: v.label as string, state: v.state as ConnectionState, hosts: [...v.hosts as string[]], scopes: [...v.scopes as string[]],
    checkedAt: v.checkedAt as number | null, message: v.message as string, ...(typeof v.enabled === "boolean" ? { enabled: v.enabled } : {}) };
}

function parseStep(value: unknown): Step | null {
  if (!object(value) || !clean(value)) return null;
  const v = value;
  if (typeof v.id !== "string" || !ID.test(v.id) || typeof v.capability !== "string" || !ID.test(v.capability)) return null;
  if (!text(v.label, 120) || !text(v.preview, 4000) || !STEP_STATUSES.includes(v.status as StepStatus)) return null;
  let result: StepResult | undefined;
  if (v.result !== undefined && v.result !== null) {
    const r = v.result;
    if (!object(r) || !clean(r) || !text(r.message, 600) || typeof r.verified !== "boolean" || !time(r.at)) return null;
    result = { message: r.message as string, verified: r.verified, at: r.at as number };
  }
  // Strict: the only reason is "blocked-by-unknown", and only on a skipped step (it never started). An absent field
  // means no reason; any other value, including an explicit null, is a malformed reply.
  let reason: StepReason | undefined;
  if (v.reason !== undefined) {
    if (v.reason !== "blocked-by-unknown" || v.status !== "skipped") return null;
    reason = v.reason;
  }
  return { id: v.id, capability: v.capability, label: v.label as string, preview: v.preview as string, status: v.status as StepStatus, ...(result ? { result } : {}), ...(reason ? { reason } : {}) };
}

export function parsePlan(value: unknown): Plan | null {
  if (!object(value) || !clean(value)) return null;
  const v = value;
  if (typeof v.id !== "string" || !TOKEN.test(v.id) || typeof v.fingerprint !== "string" || !TOKEN.test(v.fingerprint)) return null;
  if (!Number.isInteger(v.revision) || (v.revision as number) < 1 || !PLAN_STATUSES.includes(v.status as PlanStatus)) return null;
  if (!text(v.title, 120) || !time(v.createdAt) || !time(v.expiresAt) || typeof v.rememberable !== "boolean") return null;
  if (v.cancelRequested !== undefined && typeof v.cancelRequested !== "boolean") return null;
  if (!Array.isArray(v.steps) || v.steps.length < 1 || v.steps.length > MAX_STEPS) return null;
  const steps = v.steps.map(parseStep);
  if (steps.some(s => s === null) || new Set(steps.map(s => s!.id)).size !== steps.length) return null;
  return { id: v.id, revision: v.revision as number, fingerprint: v.fingerprint, status: v.status as PlanStatus, title: v.title as string,
    createdAt: v.createdAt as number, expiresAt: v.expiresAt as number, rememberable: v.rememberable, steps: steps as Step[],
    ...(v.cancelRequested ? { cancelRequested: true } : {}) };
}

/** A whole response: version 1, a server clock, and a list in which every record is valid. */
function envelope(data: unknown) {
  if (!object(data) || data.version !== VERSION || !time(data.serverNow)) throw new IntegrationError("June returned an unexpected integrations reply.", 502, "invalid-reply");
  return data;
}
export function list<T>(data: Record<string, unknown>, key: string, parse: (v: unknown) => T | null, max: number): T[] {
  const raw = data[key];
  if (!Array.isArray(raw) || raw.length > max) throw new IntegrationError("June returned an unexpected integrations reply.", 502, "invalid-reply");
  const parsed = raw.map(parse);
  if (parsed.some(item => item === null)) throw new IntegrationError("June returned an unexpected integrations reply.", 502, "invalid-reply");
  return parsed as T[];
}

export class IntegrationError extends Error {
  constructor(message: string, readonly status: number, readonly code: string) { super(message); }
}
export const isConflict = (failure: unknown) => failure instanceof IntegrationError && failure.status === 409;

export async function call(http: Http, url: string, body?: unknown) {
  const response = await http(url, body === undefined ? { cache: "no-store" } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const failure = object(data) ? data : {};
    throw new IntegrationError(typeof failure.message === "string" && failure.message.trim() ? failure.message.slice(0, 300) : "June could not reach Integrations. Try again.",
      response.status, typeof failure.code === "string" ? failure.code : "unavailable");
  }
  return envelope(data);
}

export async function getCapabilities(http: Http = defaultHttp): Promise<Reply<{ capabilities: Capability[] }>> {
  const data = await call(http, "/api/capabilities");
  return { serverNow: data.serverNow as number, capabilities: list(data, "capabilities", parseCapability, 200) };
}
export async function getConnections(http: Http = defaultHttp): Promise<Reply<{ connections: Connection[] }>> {
  const data = await call(http, "/api/connections");
  return { serverNow: data.serverNow as number, connections: list(data, "connections", parseConnection, 50) };
}
export async function getPlans(http: Http = defaultHttp): Promise<Reply<{ plans: Plan[] }>> {
  const data = await call(http, "/api/plans");
  return { serverNow: data.serverNow as number, plans: list(data, "plans", parsePlan, 20) };
}
export async function getPlan(id: string, http: Http = defaultHttp): Promise<Reply<{ plan: Plan }>> {
  return planReply(await call(http, `/api/plans/${encodeURIComponent(id)}`), id);
}
function planReply(data: Record<string, unknown>, id?: string): Reply<{ plan: Plan }> {
  const plan = parsePlan(data.plan);
  if (!plan || (id && plan.id !== id)) throw new IntegrationError("June returned an unexpected plan. Nothing else was done.", 502, "invalid-reply");
  return { serverNow: data.serverNow as number, plan };
}

/**
 * Sends one request; a dropped connection is retried once with the SAME requestId (the
 * server treats it as a replay, never a second request). A second drop means the outcome
 * is unknown: the caller reads the plan back instead of guessing.
 */
export async function idempotent(http: Http, url: string, body: Record<string, unknown>) {
  for (let attempt = 0; ; attempt++) {
    try { return await call(http, url, body); }
    catch (failure) { if (!(failure instanceof TypeError) || attempt) throw failure; }
  }
}

export type AppEntry = { id: string; label: string; remembered: boolean };
const APP_ID = /^[a-z][a-z0-9-]{1,31}$/;
export function parseApp(value: unknown): AppEntry | null {
  if (!object(value) || !clean(value) || "bundle" in value || "bundleId" in value) return null;
  if (typeof value.id !== "string" || !APP_ID.test(value.id) || !text(value.label, 60) || typeof value.remembered !== "boolean") return null;
  return { id: value.id, label: value.label as string, remembered: value.remembered };
}
/** The apps June may open: names only. Bundle ids and paths stay on the server. */
export async function getApps(http: Http = defaultHttp): Promise<Reply<{ apps: AppEntry[] }>> {
  const data = await call(http, "/api/apps");
  return { serverNow: data.serverNow as number, apps: list(data, "apps", parseApp, 40) };
}
export type PlanInput = { apps: string[] } | { op: "next" | "previous" | "pause" | "resume" } | { query: string; what: "any" | "artist" | "album" | "song" }
  | { minutes: number } | { mode: "dark" | "light" | "toggle" } | { format: "png" | "jpeg"; width?: number }
  | { name: string } | { name: string; message: string } | { name: string; recipe: "test" | "build" } | { id: string } | { ids: string[] };
const QUERY = /^[\p{L}\p{N} .,'&!+-]{1,80}$/u;
/** The only arguments the page may send: registry ids and fixed words, never a command or path. */
function checkedInput(intent: Intent, input?: PlanInput) {
  if (input === undefined) return undefined;
  const bad = () => new IntegrationError("June cannot plan that request.", 400, "invalid-input");
  if (intent === "open-app" && "apps" in input) {
    const apps = input.apps;
    if (!Array.isArray(apps) || apps.length < 1 || apps.length > 3 || new Set(apps).size !== apps.length || !apps.every(a => typeof a === "string" && APP_ID.test(a))) throw bad();
    return { apps: [...apps] };
  }
  if (intent === "music-control" && "op" in input) {
    if (!["next", "previous", "pause", "resume"].includes(input.op)) throw bad();
    return { op: input.op };
  }
  if (intent === "music-library" && "query" in input) {
    if (typeof input.query !== "string" || !QUERY.test(input.query) || !input.query.trim() || !["any", "artist", "album", "song"].includes(input.what)) throw bad();
    return { query: input.query.trim(), what: input.what };
  }
  const exact = (...keys: string[]) => Object.keys(input).every(k => keys.includes(k));
  if (intent === "keep-awake" && "minutes" in input) {
    if (!exact("minutes") || !Number.isInteger(input.minutes) || input.minutes < 1 || input.minutes > 720) throw bad();
    return { minutes: input.minutes };
  }
  if (intent === "appearance" && "mode" in input) {
    if (!exact("mode") || !["dark", "light", "toggle"].includes(input.mode)) throw bad();
    return { mode: input.mode };
  }
  if (intent === "convert-images" && "format" in input) {
    const width = input.width;
    if (!exact("format", "width") || !["png", "jpeg"].includes(input.format) || (width !== undefined && (!Number.isInteger(width) || width < 16 || width > 10000))) throw bad();
    return { format: input.format, ...(width !== undefined ? { width } : {}) };
  }
  const PROJECT = /^[\p{L}\p{N}][\p{L}\p{N} ._-]{0,59}$/u;
  if (intent === "project-pull" && "name" in input) {
    if (!exact("name") || !PROJECT.test(input.name)) throw bad();
    return { name: input.name };
  }
  if (intent === "project-push" && "message" in input) {
    const message = input.message;
    if (!exact("name", "message") || !PROJECT.test(input.name) || typeof message !== "string" || !message.trim() || message.length > 200 || /[\u0000-\u001f\u007f]/.test(message)) throw bad();
    return { name: input.name, message: message.trim() };
  }
  if (intent === "project-recipe" && "recipe" in input) {
    if (!exact("name", "recipe") || !PROJECT.test(input.name) || !["test", "build"].includes(input.recipe)) throw bad();
    return { name: input.name, recipe: input.recipe };
  }
  if (intent === "job-apply" && "ids" in input) {
    const ids = input.ids;
    if (!exact("ids") || !Array.isArray(ids) || ids.length < 1 || ids.length > 5 || new Set(ids).size !== ids.length || !ids.every(id => typeof id === "string" && /^\d{8,16}$/.test(id))) throw bad();
    return { ids };
  }
  if ((intent === "project-command" || intent === "project-stop" || intent === "site-publish" || intent === "site-unpublish" || intent === "site-rollback") && "id" in input) {
    if (!exact("id") || typeof input.id !== "string" || !/^[a-f0-9]{32}$/.test(input.id)) throw bad();
    return { id: input.id };
  }
  throw bad();
}

export async function proposePlan(intent: Intent, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID(), input?: PlanInput) {
  if (!INTENTS.includes(intent)) throw new IntegrationError("June cannot plan that yet.", 400, "unknown-intent");
  const checked = checkedInput(intent, input);
  try { return planReply(await idempotent(http, "/api/plans", { requestId: uuid(), intent, ...(checked ? { input: checked } : {}) })); }
  catch (failure) {
    if (failure instanceof TypeError) throw new IntegrationError("June could not confirm whether the request was received. Check Plans before asking again.", 0, "outcome-unknown");
    throw failure;
  }
}

/**
 * Approve or cancel exactly the plan the person reviewed: its id, immutable revision and
 * fingerprint. If the connection is lost twice, read the plan back rather than resend.
 */
async function decide(kind: "approve" | "cancel", reviewed: Plan, http: Http, uuid: () => string, remember?: boolean) {
  const body = { requestId: uuid(), revision: reviewed.revision, fingerprint: reviewed.fingerprint, ...(kind === "approve" && remember ? { remember: true } : {}) };
  try { return { ...planReply(await idempotent(http, `/api/plans/${encodeURIComponent(reviewed.id)}/${kind}`, body), reviewed.id), reconciled: false }; }
  catch (failure) {
    if (!(failure instanceof TypeError)) throw failure;
    try { return { ...await getPlan(reviewed.id, http), reconciled: true }; }
    catch { throw new IntegrationError("June could not confirm what happened. Check Plans before trying again.", 0, "outcome-unknown"); }
  }
}
export const approvePlan = (reviewed: Plan, remember = false, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) =>
  decide("approve", reviewed, http, uuid, remember && reviewed.rememberable);
export const cancelPlan = (reviewed: Plan, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) =>
  decide("cancel", reviewed, http, uuid);

// proposed → approved → running → one final outcome. A late reply never moves a plan
// backwards, and the first final outcome seen is kept. A higher revision is a new payload.
const RANK: Record<PlanStatus, number> = { proposed: 0, approved: 1, running: 2, completed: 3, partial: 3, failed: 3, cancelled: 3, expired: 3, unknown: 3 };
// Steps follow the same rule: pending → running → one final outcome, first final outcome kept.
const STEP_RANK: Record<StepStatus, number> = { pending: 0, running: 1, completed: 2, failed: 2, skipped: 2, cancelled: 2, unknown: 2 };
function mergeStep(current: Step | undefined, incoming: Step): Step {
  if (!current) return incoming;
  if (STEP_RANK[current.status] > STEP_RANK[incoming.status] || (STEP_RANK[current.status] === 2 && current.status !== incoming.status)) return current;
  return incoming.result || !current.result ? incoming : { ...incoming, result: current.result };
}
export function mergePlan(current: Plan | undefined, incoming: Plan) {
  if (!current || current.id !== incoming.id || incoming.revision > current.revision) return incoming;
  if (incoming.revision < current.revision) return current;
  const status = RANK[current.status] > RANK[incoming.status] || (RANK[current.status] === 3 && current.status !== incoming.status) ? current.status : incoming.status;
  const known = new Map(current.steps.map(s => [s.id, s]));
  return { ...incoming, status, steps: incoming.steps.map(s => mergeStep(known.get(s.id), s)),
    ...(current.cancelRequested || incoming.cancelRequested ? { cancelRequested: true } : {}) };
}
/** The server's newest list (incoming order), each known plan merged monotonically. */
export function mergePlans(current: readonly Plan[], incoming: readonly Plan[]) {
  const known = new Map(current.map(p => [p.id, p]));
  const merged = incoming.map(p => mergePlan(known.get(p.id), p));
  const seen = new Set(merged.map(p => p.id));
  return [...merged, ...current.filter(p => !seen.has(p.id))].slice(0, 20);
}

/**
 * Forget every remembered tool approval (and the matching Hands setting). Repeatable and
 * never grants anything; the server replies with the current plan list.
 */
export async function forgetApprovals(http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()): Promise<Reply<{ plans: Plan[] }>> {
  const data = await idempotent(http, "/api/plans/forget", { requestId: uuid() });
  return { serverNow: data.serverNow as number, plans: list(data, "plans", parsePlan, 20) };
}

export const FINAL: readonly PlanStatus[] = ["completed", "partial", "failed", "cancelled", "expired", "unknown"];
export const isActive = (plan: Plan) => plan.status === "approved" || plan.status === "running";

export const PLAN_WORDS: Record<PlanStatus, string> = {
  proposed: "Waiting for your review",
  approved: "Approved · starting",
  running: "Running",
  completed: "Done · each step checked",
  partial: "Partly done · see each step",
  failed: "Did not complete",
  cancelled: "Cancelled · nothing more will run",
  expired: "Expired · nothing ran",
  unknown: "Outcome unknown · check before asking again",
};
export const STEP_WORDS: Record<StepStatus, string> = {
  pending: "Not started", running: "Running", completed: "Done", failed: "Failed",
  skipped: "Skipped", cancelled: "Cancelled", unknown: "Outcome unknown",
};
/** A step's status in words. A step skipped because an earlier one is unconfirmed says it never started, and why;
 * a plain skip (for example after a cancellation) stays "Skipped". */
export function stepWords(step: Pick<Step, "status" | "reason" | "capability">) {
  if (step.status === "skipped" && step.reason === "blocked-by-unknown")
    return `Not started — previous ${step.capability === "jobs.apply" ? "application" : "step"} not confirmed`;
  return STEP_WORDS[step.status];
}
/** Outcome counts for a plan's steps; confirmed, unconfirmed and never-started are kept apart. */
export function planCounts(plan: Pick<Plan, "steps">) {
  const counts = { confirmed: 0, unconfirmed: 0, notStarted: 0, failed: 0, cancelled: 0, skipped: 0 };
  for (const step of plan.steps) {
    if (step.status === "completed") counts.confirmed++;
    else if (step.status === "unknown") counts.unconfirmed++;
    else if (step.status === "skipped" && step.reason === "blocked-by-unknown") counts.notStarted++;
    else if (step.status === "failed") counts.failed++;
    else if (step.status === "cancelled") counts.cancelled++;
    else if (step.status === "skipped") counts.skipped++;
  }
  return counts;
}
/** One line summarising a finished multi-step plan ("2 confirmed · 1 not confirmed · 3 not started"); empty otherwise. */
export function countsLine(plan: Pick<Plan, "steps" | "status">) {
  if (plan.steps.length < 2 || ["proposed", "approved", "running"].includes(plan.status)) return "";
  const c = planCounts(plan);
  return [[c.confirmed, "confirmed"], [c.unconfirmed, "not confirmed"], [c.notStarted, "not started"], [c.failed, "failed"], [c.cancelled, "cancelled"], [c.skipped, "skipped"]]
    .filter(([n]) => (n as number) > 0).map(([n, word]) => `${n} ${word}`).join(" · ");
}
export const CONNECTION_WORDS: Record<ConnectionState, string> = {
  "not-configured": "Not set up", "needs-consent": "Needs your permission", connected: "Connected",
  expired: "Expired · reconnect needed", revoked: "Access removed", error: "Error", unsupported: "Not available yet",
};
export const RISK_WORDS: Record<Risk, string> = { read: "Reads only", local: "Changes this Mac", outward: "Sends or publishes", financial: "Money" };

/** Time left on the server's deadline, advanced by local time since the server spoke. */
export function remainingMs(plan: Plan, serverNow: number, receivedAt: number, now: number) {
  return plan.expiresAt - (serverNow + Math.max(0, now - receivedAt));
}
