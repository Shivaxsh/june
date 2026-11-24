// June's approved Mac actions. The server proposes a fixed, allowlisted action;
// the person approves the exact record with a click. Nothing here builds a
// command: the browser only ever sends an id and the server's fingerprint.

export const ACTIONS = ["open-vscode", "open-project"] as const;
export type ActionName = typeof ACTIONS[number];
export const STATUSES = ["proposed", "executing", "completed", "unverified", "failed", "cancelled", "expired"] as const;
export type ActionStatus = typeof STATUSES[number];
export type ActionResult = { state: "active" | "running" | "unverified" | "failed"; message: string };
export type ActionRecord = {
  id: string; action: ActionName; label: string; detail: string; fingerprint: string;
  createdAt: number; expiresAt: number; status: ActionStatus; result?: ActionResult;
  /** 'direct' when the person's no-review setting ran it; absent or 'approved' after a click on Approve. */
  mode?: "approved" | "direct";
  projectId?: string; projectPath?: string;
};
export type Project = { id: string; name: string; folderPath: string; remembered: boolean };
export type ActionState = { projects?: Project[]; serverNow: number; available: boolean; actions: ActionRecord[]; appState?: AppState; observedAt?: number; openVSCodeWithoutApproval: boolean };
type Http = (url: string, init?: RequestInit) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

const ID = /^[\w-]{8,128}$/;
// A server record never carries anything executable; refuse one that tries.
const FORBIDDEN = ["command", "argv", "args", "path", "shell", "cwd"];
const RESULT_STATES = ["active", "running", "unverified", "failed"];
const text = (value: unknown, max: number) => typeof value === "string" && value.trim().length > 0 && value.length <= max;
const time = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0;

export function parseAction(value: unknown): ActionRecord | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  if (FORBIDDEN.some(key => key in v)) return null;
  if (!ACTIONS.includes(v.action as ActionName) || !STATUSES.includes(v.status as ActionStatus)) return null;
  if (typeof v.id !== "string" || !ID.test(v.id) || typeof v.fingerprint !== "string" || !ID.test(v.fingerprint)) return null;
  if (!text(v.label, 80) || !text(v.detail, 1200) || !time(v.createdAt) || !time(v.expiresAt)) return null;
  if (v.mode !== undefined && v.mode !== "approved" && v.mode !== "direct") return null;
  if (v.action === "open-project" && (typeof v.projectId !== "string" || !ID.test(v.projectId) || !text(v.projectPath, 1024) || !(v.projectPath as string).startsWith("/"))) return null;
  let result: ActionResult | undefined;
  if (v.result !== undefined && v.result !== null) {
    const r = v.result as Record<string, unknown>;
    if (typeof r !== "object" || !RESULT_STATES.includes(r.state as string) || (r.message !== undefined && typeof r.message !== "string")) return null;
    result = { state: r.state as ActionResult["state"], message: typeof r.message === "string" ? r.message.slice(0, 300) : "" };
  }
  return { id: v.id, action: v.action as ActionName, label: v.label as string, detail: v.detail as string, fingerprint: v.fingerprint,
    createdAt: v.createdAt as number, expiresAt: v.expiresAt as number, status: v.status as ActionStatus, ...(result ? { result } : {}),
    ...(v.action === "open-project" ? { projectId: v.projectId as string, projectPath: v.projectPath as string } : {}),
    ...(v.mode ? { mode: v.mode as "approved" | "direct" } : {}) };
}

export function parseState(value: unknown): ActionState | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (!time(v.serverNow) || !Array.isArray(v.actions)) return null;
  return { serverNow: v.serverNow as number, available: v.available === true, openVSCodeWithoutApproval: v.openVSCodeWithoutApproval === true,
    ...(Array.isArray(v.projects) ? { projects: v.projects.filter((p): p is Project => !!p && typeof p === "object" && typeof p.id === "string" && ID.test(p.id) && text(p.name,60) && text(p.folderPath,1024) && p.folderPath.startsWith("/") && typeof p.remembered === "boolean") } : {}),
    actions: v.actions.map(parseAction).filter((a): a is ActionRecord => a !== null),
    ...(APP_STATES.includes(v.appState as AppState) ? { appState: v.appState as AppState } : {}),
    ...(time(v.observedAt) ? { observedAt: v.observedAt as number } : {}) };
}

/** Time left on the server's deadline, advanced by local time elapsed since the server spoke. */
export function remainingMs(record: ActionRecord, serverNow: number, receivedAt: number, now: number) {
  return record.expiresAt - (serverNow + Math.max(0, now - receivedAt));
}
export function formatRemaining(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// Words describe what macOS was observed doing after approval. VS Code may already have been
// open, so nothing here claims June launched it.
export const STATUS_WORDS: Record<string, string> = {
  proposed: "Waiting for your approval",
  executing: "Opening or bringing VS Code forward…",
  active: "VS Code is open and in front",
  running: "VS Code is running · it may be behind another window",
  // After a restart June may have stopped before asking the Mac at all, so only the uncertainty is stated.
  unverified: "Outcome unverified · June could not confirm VS Code is open. It will not retry.",
  failed: "Did not open",
  cancelled: "Cancelled · nothing ran",
  expired: "Expired · nothing ran",
};
const PAST: Record<string, string> = { active: "Seen open and in front after approval", running: "Seen running after approval" };
const PAST_DIRECT: Record<string, string> = { active: "Seen open and in front after opening · no review (your setting)", running: "Seen running after opening · no review (your setting)" };
/** Wording comes from the observed result, never from a launch exit code. `past` is for history rows. */
export function statusText(record: ActionRecord, { past = false } = {}) {
  if (record.action === "open-project" && (record.status === "completed" || record.status === "unverified")) return record.result?.message || "Folder request outcome unverified. Check VS Code.";
  if (record.status === "completed" || record.status === "unverified") {
    const state = record.result?.state === "active" || record.result?.state === "running" ? record.result.state : "unverified";
    const history = record.mode === "direct" ? PAST_DIRECT : PAST;
    return past && history[state] ? history[state] : STATUS_WORDS[state];
  }
  if (record.status === "failed") return record.result?.message ? `${STATUS_WORDS.failed} · ${record.result.message}` : STATUS_WORDS.failed;
  return STATUS_WORDS[record.status];
}

/** A snapshot of VS Code as macOS reported it when June last checked: not a live monitor. */
export const APP_STATES = ["active", "running", "not-running", "unverified"] as const;
export type AppState = typeof APP_STATES[number];
export const APP_STATE_WORDS: Record<AppState, string> = { active: "Active · in front", running: "Already running", "not-running": "Not running", unverified: "Could not verify" };
/** How long ago the snapshot was taken, on the server clock advanced by local time since the reply. */
export function observedAgo(observedAt: number | undefined, serverNow: number, receivedAt: number, now: number) {
  if (observedAt === undefined) return "";
  const s = Math.max(0, Math.floor((serverNow + Math.max(0, now - receivedAt) - observedAt) / 1000));
  return s < 2 ? "checked just now" : s < 60 ? `checked ${s} s ago` : `checked ${Math.floor(s / 60)} min ago`;
}

async function call(http: Http, url: string, body?: unknown) {
  const response = await http(url, body === undefined ? { cache: "no-store" } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
  const data = await response.json().catch(() => null) as Record<string, unknown> | null;
  if (!response.ok) throw new Error(typeof data?.message === "string" ? data.message : "June could not reach Hands. Try again.");
  return data;
}
function actionReply(data: Record<string, unknown> | null, id?: string) {
  const action = parseAction(data?.action);
  if (!action || !time(data?.serverNow) || (id && action.id !== id)) throw new Error("June returned an unexpected action. Nothing else was done.");
  return { serverNow: data!.serverNow as number, action, reconciled: false };
}

// proposed → executing → one final outcome. A late reply can never move a record backwards,
// and the first outcome seen is kept: the server never changes an outcome once recorded.
const RANK: Record<ActionStatus, number> = { proposed: 0, executing: 1, completed: 2, unverified: 2, failed: 2, cancelled: 2, expired: 2 };
export function mergeAction(current: ActionRecord | undefined, incoming: ActionRecord) {
  if (!current || current.id !== incoming.id) return incoming;
  if (RANK[current.status] > RANK[incoming.status] || (RANK[current.status] === 2 && current.status !== incoming.status)) return current;
  return incoming;
}
/** The server's newest list, with each known record merged monotonically; incoming order wins. */
export function mergeActions(current: readonly ActionRecord[], incoming: readonly ActionRecord[]) {
  const known = new Map(current.map(a => [a.id, a]));
  const merged = incoming.map(a => mergeAction(known.get(a.id), a));
  const seen = new Set(merged.map(a => a.id));
  return [...merged, ...current.filter(a => !seen.has(a.id))];
}

const defaultHttp: Http = (url, init) => fetch(url, init);
export async function getActions(http: Http = defaultHttp) {
  const state = parseState(await call(http, "/api/actions"));
  if (!state) throw new Error("June returned an unexpected Hands state.");
  return state;
}
export async function proposeAction(http: Http = defaultHttp) {
  return actionReply(await call(http, "/api/actions/propose", { action: "open-vscode" }));
}
/**
 * One POST with the exact fingerprint. If the connection drops, June may or may not
 * have acted: read the state back instead of sending the approval again.
 */
async function decide(kind: "approve" | "cancel", record: ActionRecord, http: Http, remember?: boolean) {
  let data: Record<string, unknown> | null;
  try {
    data = await call(http, `/api/actions/${encodeURIComponent(record.id)}/${kind}`, { fingerprint: record.fingerprint, ...(remember === undefined ? {} : { remember }) });
  } catch (failure) {
    if (!(failure instanceof TypeError)) throw failure;
    const state = await getActions(http);
    const current = state.actions.find(a => a.id === record.id);
    if (!current) throw new Error("June could not confirm what happened. Check Hands before trying again.");
    return { serverNow: state.serverNow, action: current, reconciled: true };
  }
  return actionReply(data, record.id);
}
/** `remember` asks the server to trust this same fixed action next time; it only takes effect with a genuine bound approval. */
export const approveAction = (record: ActionRecord, http: Http = defaultHttp, remember?: boolean) => decide("approve", record, http, remember);
export const cancelAction = (record: ActionRecord, http: Http = defaultHttp) => decide("cancel", record, http);

/** Turning the no-review setting on or off; the server replies with the full Hands state. */
export async function setOpenWithoutApproval(value: boolean, http: Http = defaultHttp) {
  const state = parseState(await call(http, "/api/actions/preferences", { openVSCodeWithoutApproval: value }));
  if (!state) throw new Error("June returned an unexpected Hands state.");
  return state;
}
/**
 * Open VS Code directly (only when the setting is on). Idempotent on requestId: a dropped
 * connection is retried once with the same id, so VS Code is never asked twice for one click.
 */
export async function runOpenVSCode(http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  const body = { action: "open-vscode", requestId: uuid() };
  for (let attempt = 0; ; attempt++) {
    try { return actionReply(await call(http, "/api/actions/run", body)); }
    catch (failure) {
      if (!(failure instanceof TypeError)) throw failure;
      if (attempt) throw new Error("June could not confirm whether VS Code was opened. Check Hands before trying again.");
    }
  }
}

export async function proposeProject(projectId: string, http: Http = defaultHttp) {
  return actionReply(await call(http, "/api/actions/propose", { action: "open-project", projectId }));
}
export async function runProject(projectId: string, http: Http = defaultHttp, uuid: () => string = () => crypto.randomUUID()) {
  const body = { action: "open-project", projectId, requestId: uuid() };
  for (let attempt = 0; ; attempt++) {
    try { return actionReply(await call(http, "/api/actions/run", body)); }
    catch (error) { if (!(error instanceof TypeError)) throw error; if (attempt) throw new Error("Folder request outcome unknown. Check Hands before trying again."); }
  }
}
export async function changeProject(kind: "add" | "remove" | "forget", value: {name: string; path: string} | {id: string}, http: Http = defaultHttp) {
  const url = kind === "add" ? "/api/actions/projects" : `/api/actions/projects/${encodeURIComponent((value as {id:string}).id)}/${kind}`;
  const state = parseState(await call(http, url, kind === "add" ? value : {}));
  if (!state) throw new Error("Unexpected project settings. Refresh Hands.");
  return state;
}
