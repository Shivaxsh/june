// Automatic recovery for June's local voice. The page keeps checking audio
// status while it is preparing or unavailable, at a bounded, slowing pace, and
// reloads the voice list when audio becomes ready again. It never opens the
// microphone or replays speech, and it cannot repair the Mac's audio service.

export type AudioPhase = "ready" | "preparing" | "unavailable";
/** `outputError` is the backend's positive report that playback failed; `voiceWarm` alone is not (prewarm may be off). */
export type AudioStatusLike = { state?: string; nativeReady?: boolean; providerState?: string; voiceWarm?: boolean; modelWarm?: boolean; outputError?: string | null };

export const MAX_PREPARING_CHECKS = 90;   // 30 × 2 s, then 60 × 5 s ≈ 6 minutes
export const MAX_UNAVAILABLE_CHECKS = 12; // 2, 4, 8, 16, 32, then 60 s ≈ 8 minutes
/** A ready, visible page still checks slowly, so a helper that dies while idle is noticed without a reload. */
export const HEALTHY_CHECK_MS = 30_000;

/** Can June's voice play right now? A reported output failure says no, whatever else is ready. */
export function outputUsable(status: AudioStatusLike) {
  return status.nativeReady === true && status.providerState === "ready" && !status.outputError;
}

export function audioPhase(status: AudioStatusLike): AudioPhase {
  if (status.outputError) return "unavailable";
  if (status.state === "ready") return status.nativeReady === true && status.providerState === "ready" ? "ready" : "unavailable";
  return status.state === "preparing" || status.state === "checking" ? "preparing" : "unavailable";
}

/** Milliseconds until the next status check, or null to stop (ready, or the budget is spent). */
export function nextCheckDelay(phase: AudioPhase, attempt: number): number | null {
  if (phase === "ready") return HEALTHY_CHECK_MS;
  if (phase === "preparing") return attempt >= MAX_PREPARING_CHECKS ? null : attempt < 30 ? 2000 : 5000;
  return attempt >= MAX_UNAVAILABLE_CHECKS ? null : Math.min(60000, 2000 * 2 ** attempt);
}

/**
 * Spending a timer's single spoken announcement needs output that is prepared: voiceWarm, or a
 * ready status when prewarm is off (the backend then never reports warm). A cold model never matters.
 */
export function alertOutputWarm(status: AudioStatusLike) {
  return !status.outputError && (status.voiceWarm === true || status.state === "ready");
}

/** The first mount loads the voice list itself; afterwards reload it whenever audio comes back. */
export function shouldReloadVoices(before: AudioPhase | undefined, now: AudioPhase) {
  return now === "ready" && before !== undefined && before !== "ready";
}

export function recoveryMessage({ phase, gaveUp, delayMs, outputError = false }: { phase: AudioPhase; gaveUp: boolean; delayMs: number; outputError?: boolean }) {
  if (phase === "ready") return "";
  if (gaveUp) return "Automatic audio checks have paused. Check Mac Sound settings and choose Refresh audio to retry. Replies stay readable.";
  if (phase === "preparing") return "Preparing June’s voice… replies stay readable meanwhile.";
  const seconds = Math.round(delayMs / 1000);
  if (outputError) return `June’s voice output stopped working. Checking again in ${seconds} s; replies stay readable.`;
  return `June’s voice is unavailable. Checking again in ${seconds} s; replies stay readable.`;
}
