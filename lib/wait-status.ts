// What June shows while a reply is on its way: only stages the server reported,
// plus measured time since the request. Never an estimate or invented progress.
const LABELS = {
  queued: "Waiting for the model",
  loading: "Loading the model",
  searching: "Searching documents",
  answering: "Preparing an answer",
} as const;
export type WaitStage = keyof typeof LABELS;
export function isWaitStage(stage: unknown): stage is WaitStage { return typeof stage === "string" && Object.hasOwn(LABELS, stage); }
export function waitLabel(stage: string, { continuing = false } = {}) {
  return isWaitStage(stage) ? LABELS[stage] : continuing ? "Continuing" : "Thinking";
}
/** Measured wall-clock time, shown from 3 s so short replies stay quiet. */
export function elapsedText(ms: number) {
  if (!(ms >= 3000)) return "";
  const s = Math.floor(ms / 1000);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}
