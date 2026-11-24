// Continuing a reply that stopped at the length limit.
// Each continuation is saved as its own segment linked to the one before it;
// the screen joins the chain into one bubble and the latest segment decides
// whether June still owes the rest.
import type { SavedTurn } from "./memory-types";

export const CONTINUE_PROMPT = "Continue.";
export const LIMIT_NOTICE = "I hit my length limit. Say continue for the rest.";
export const INCOMPLETE_NOTICE = "The code may be unfinished. Say continue for the rest.";
export const CODE_NOTICE = "The code is on screen.";

const INTENT = /^\s*(?:(?:ok(?:ay)?|yes|yeah|please|so|now|hey june|june)[\s,.!]+)*(?:continue|keep going|go on|carry on|finish (?:it|that|the (?:code|reply|answer|rest)))(?:\s+(?:please|(?:from )?where you (?:stopped|left off)|with the rest|the rest))*[\s,.!]*$/i;
/** "continue", "keep going", "Hey June, continue please" — not "continue the story about…". */
export function isContinueIntent(text: string) { return INTENT.test(text); }

/** The run (``` / ~~~ / ````) of a code fence opened and never closed, or null. */
export function openFence(text: string) {
  // Same rule as the server (reply_state.open_fence): a closing fence uses the opening
  // character, is at least as long, and has nothing after it.
  let open: string | null = null;
  for (const line of text.split("\n")) {
    const match = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
    if (!match) continue;
    const [, run, rest] = match;
    if (open === null) open = run;
    else if (run[0] === open[0] && run.length >= open.length && !rest.trim()) open = null;
  }
  return open;
}
/** True when a code fence is opened and never closed. Balanced fences say nothing about whether code is valid. */
export function unclosedFence(text: string) { return openFence(text) !== null; }
/**
 * Speech-only prefix for a continuation: when the saved reply left a fence open, the
 * continued code is wrapped in a matching opening fence so speech cleanup drops it.
 * It never reaches displayed or saved text.
 */
export function speechLead(base: string) { const run = openFence(base); return run ? `${run}\n` : ""; }

const flag = (value: unknown) => value === true || value === 1;
export type ContinuationFlags = { limited?: boolean | number; incomplete?: boolean | number; continuedFrom?: string | null };
export type JoinedTurn = { id: string; latestId: string; user: string; parts: string[]; status: SavedTurn["status"]; limited: boolean; incomplete: boolean; memories: string; citations: SavedTurn["citations"]; actionId?: string | null; timerId?: string | null; reminderId?: string | null; reminderSeriesId?: string | null };

/** Saved segments → display turns. Only a complete segment that follows the chain's latest segment joins it. */
export function joinTurns(turns: readonly (SavedTurn & ContinuationFlags)[]) {
  const joined: JoinedTurn[] = [];
  for (const t of turns) {
    if (t.continuedFrom) {
      // The chain may sit behind a completeness notice, so find it by its latest segment, not position.
      const owner = joined.findLast(j => j.latestId === t.continuedFrom);
      // A stopped or failed continuation was never part of the saved chain; June continues from the segment before it.
      if (owner && t.status !== "complete") continue;
      if (owner && owner.status === "complete") {
        owner.parts.push(t.assistant); owner.latestId = t.id; owner.status = t.status;
        owner.limited = flag(t.limited); owner.incomplete = flag(t.incomplete);
        continue;
      }
    }
    joined.push({ id: t.id, latestId: t.id, user: t.user, parts: [t.assistant], status: t.status, limited: flag(t.limited), incomplete: flag(t.incomplete), memories: t.memories, citations: t.citations, ...(t.actionId ? { actionId: t.actionId } : {}), ...(t.timerId ? { timerId: t.timerId } : {}), ...(t.reminderId ? { reminderId: t.reminderId } : {}), ...(t.reminderSeriesId ? { reminderSeriesId: t.reminderSeriesId } : {}) });
  }
  return joined;
}

/** One fixed line, spoken after the reply: never the code itself, never a claim that code works. */
export function spokenNotice({ limited, incomplete, spokeSomething, hasCode }: { limited: boolean; incomplete: boolean; spokeSomething: boolean; hasCode: boolean }) {
  const lines: string[] = [];
  if (!spokeSomething && hasCode) lines.push(CODE_NOTICE);
  if (limited) lines.push(LIMIT_NOTICE); else if (incomplete) lines.push(INCOMPLETE_NOTICE);
  return lines.join(" ");
}
