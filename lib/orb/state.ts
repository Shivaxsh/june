export type Mood = "idle" | "listening" | "thinking" | "speaking";
export type AudioPhase = "idle" | "playing" | "paused" | "requesting" | "listening";
export type Preview = Mood | "auto";

// The chat owns priority; media remains independently visible in its controls.
export function resolveOrb(busy: boolean, demo: boolean, preview: Preview, audio: AudioPhase) {
  if (busy) return { mood: "thinking" as Mood, label: demo ? "Generating · simulated reply" : "Generating reply" };
  if (preview !== "auto") return { mood: preview, label: `${preview[0].toUpperCase()}${preview.slice(1)} · visual preview` };
  if (audio === "listening") return { mood: "listening" as Mood, label: "Listening · sound visualisation only" };
  if (audio === "playing") return { mood: "speaking" as Mood, label: "Audio playback" };
  return { mood: "idle" as Mood, label: "Idle · ready when you are" };
}
