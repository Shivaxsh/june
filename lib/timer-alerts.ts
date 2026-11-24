// The spoken-alert queue for finished timers. Each alert names its timer, so a
// timer dismissed or cancelled before June is free is dropped, never spoken late.
/** Anything with a completion state: timers and reminders share this queue under namespaced ids. */
type Alertable = { id: string; status: string };

export type TimerAlert = { id: string; phrase: string };
/** Set when an alert starts; it holds the queue until that speech has begun and ended. */
export type AlertGate = { since: number; heard: boolean } | null;
/** If speech never starts (voice failed or was muted), the next alert may go after this. */
export const ALERT_START_TIMEOUT_MS = 4000;

const stillDone = (id: string, timers: readonly Alertable[]) => timers.some(t => t.id === id && t.status === "completed");

/** Queue an alert only while its timer is still completed (current, merged state) and not already queued. */
export function enqueueAlert(queue: readonly TimerAlert[], alert: TimerAlert, timers: readonly Alertable[]) {
  if (!stillDone(alert.id, timers) || queue.some(a => a.id === alert.id)) return [...queue];
  return [...queue, alert];
}

export const openGate = (now: number): AlertGate => ({ since: now, heard: false });
/** Advance the gate with June's speech phase: released after the alert was heard and ended, or never started. */
export function updateGate(gate: AlertGate, phase: string, now: number): AlertGate {
  if (!gate) return null;
  if (phase !== "idle") return gate.heard ? gate : { ...gate, heard: true };
  if (gate.heard) return null;
  return now - gate.since >= ALERT_START_TIMEOUT_MS ? null : gate;
}

/** Drop alerts whose timer is no longer completed; play the next one only when June is free and no alert is speaking. */
export function takeAlert(queue: readonly TimerAlert[], timers: readonly Alertable[], { idle, gate }: { idle: boolean; gate: AlertGate }) {
  const live = queue.filter(a => stillDone(a.id, timers));
  if (!idle || gate || !live.length) return { play: null as TimerAlert | null, queue: live };
  const [play, ...rest] = live;
  return { play, queue: rest };
}

/** A timer already finished when this page saw it is spoken only if it ended this recently. */
export const TIMER_ALERT_WINDOW_MS = 120_000;
/**
 * Whether this tab should speak a claimed timer. The server's announce:true is required (at most once).
 * A timer this page saw running always qualifies, even if a long reply delayed the claim; one that was
 * already finished when the page loaded qualifies only if it ended recently. Otherwise its card shows.
 */
export function shouldAnnounce({ announce, timer, serverNow, witnessedActive }: { announce: boolean; timer: { completedAt?: number }; serverNow: number; witnessedActive: boolean }) {
  if (!announce) return false;
  if (witnessedActive || timer.completedAt === undefined) return true;
  return serverNow - timer.completedAt <= TIMER_ALERT_WINDOW_MS;
}

/** Claiming spends the server's single announcement, so it waits for a free June with a ready, unmuted voice. */
export function alertReady({ idle, speakReplies, voiceSelected }: { idle: boolean; speakReplies: boolean; voiceSelected: string }) {
  return idle && speakReplies && voiceSelected.length > 0;
}
