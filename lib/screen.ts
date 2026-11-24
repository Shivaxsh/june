// 8.6 Screen: June reads the screen's text once when asked in chat. This file only turns that on or off.
import { call, defaultHttp, IntegrationError, type Http } from "./integrations";

export type ScreenProblem = "screen-permission" | "unavailable";
export type ScreenState = { enabled: boolean; installed: boolean; problem: ScreenProblem | null };
const PROBLEMS: ScreenProblem[] = ["screen-permission", "unavailable"];
const invalid = () => new IntegrationError("June returned the screen setting in an unexpected form.", 502, "invalid-response");

export function parseScreen(data: Record<string, unknown>): ScreenState {
  const { enabled, installed, problem } = data;
  if (typeof enabled !== "boolean" || typeof installed !== "boolean") throw invalid();
  if (problem !== undefined && problem !== null && (typeof problem !== "string" || !PROBLEMS.includes(problem as ScreenProblem))) throw invalid();
  return { enabled, installed, problem: (problem ?? null) as ScreenProblem | null };
}
export async function getScreen(http: Http = defaultHttp) { return parseScreen(await call(http, "/api/screen")); }
export async function allowScreen(allowed: boolean, http: Http = defaultHttp) { return parseScreen(await call(http, "/api/screen/enable", { allowed })); }

/** Orders replies for one panel: only the newest started request may update the screen, and only one change runs at a time. */
export function screenRequests() {
  let latest = 0, changing = false;
  return {
    /** Start a status read; the returned check says whether its reply is still the newest. */
    // A read started while a change runs could report the setting from before it, so it is ignored.
    read() { if (changing) return () => false; const id = ++latest; return () => id === latest; },
    /** Start an on/off change, or null while another change is still running (a double click). */
    change() {
      if (changing) return null;
      changing = true; const id = ++latest;
      return { current: () => id === latest, done: () => { changing = false; } };
    },
  };
}
