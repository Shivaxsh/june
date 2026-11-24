// These types describe the JSON exchanged between the browser and June's server.
export type ChatMessage = { role: "user" | "assistant"; content: string };
export type ChatMode = "local" | "demo";
export type ChatEvent =
  | { type: "stage"; stage:"queued"|"loading"|"searching"|"answering" }
  | { type: "delta"; text: string }
  | { type: "done"; model: string; citations?:import("./knowledge-types").Citation[]; provenance?:import("./knowledge-types").Provenance; knowledgeRevision?:number; limited?: boolean; incomplete?: boolean; continuedFrom?: string | null;
    /** The saved segment a Continue request would resume now (null: nothing to continue). */ resumable?: string | null;
    /** A server-proposed Mac action awaiting a click; validated by lib/actions parseAction. */ actionProposal?: unknown; /** A reviewed plan (lib/integrations parsePlan), e.g. play the chosen playlist. */ plan?: unknown; serverNow?: number;
    /** A simulated purchase or booking for this turn; validated by lib/transactions parseTransaction. */ transaction?: unknown;
    /** A timer the server started for this turn; validated by lib/timers parseTimer. */ timer?: unknown;
    /** A reminder the server saved for this turn; validated by lib/reminders parseReminder. */ reminder?: unknown;
    /** A repeating reminder created or changed in this turn; validated by lib/reminders parseSeries. */ series?: unknown; repetitionStopped?: boolean; persistence?: "saved" | "temporary"; memoryIds?: string[]; revision?: number; conversationId?: string; turnId?: string }
  | { type: "timing"; stage: string; durationMs: number }
  | { type: "error"; message: string };

export type ModelStatus = {
  state: "ready" | "offline" | "missing" | "error";
  model: string;
  message: string;
  /** The installed model's real parameter count, when Ollama reports it. */
  parameters?: number;
};

export const MAX_MESSAGE_LENGTH = 2000;
export const MAX_CONTEXT_LENGTH = 6000;
export const MAX_CONTEXT_MESSAGES = 20;
