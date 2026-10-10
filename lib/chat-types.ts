// These types describe the JSON exchanged between the browser and June's server.
export type ChatMessage = { role: "user" | "assistant"; content: string };
export type ChatMode = "local" | "demo";
export type ChatEvent =
  | { type: "delta"; text: string }
  | { type: "done"; model: string }
  | { type: "error"; message: string };

export type ModelStatus = {
  state: "ready" | "offline" | "missing" | "error";
  model: string;
  message: string;
};

export const MAX_MESSAGE_LENGTH = 2000;
export const MAX_CONTEXT_LENGTH = 6000;
export const MAX_CONTEXT_MESSAGES = 20;
