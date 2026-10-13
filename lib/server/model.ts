import type { ChatEvent, ChatMessage, ChatMode, ModelStatus } from "../chat-types";
import { readJsonLines } from "../ndjson";

// The prompt belongs on the server. The client cannot supply system messages.
export const JUNE_PROMPT = `You are June, Shivansh's warm and concise personal AI assistant, using she/her pronouns. Help the user with questions, explanations and ideas. Answer the actual question directly in plain text, usually under 120 words. You are version 0.3. Your browser interface can transcribe voice requests and read replies aloud when speech support is available; your language model runs locally. Use the current conversation for context. Personal facts about the user must come from what they told you here; if a requested personal fact is missing, acknowledge that you do not know it. Be honest about uncertainty. You have no memory across sessions and cannot browse, control devices, access accounts or make purchases. Never claim you performed those actions.`;

function settings() {
  const url = new URL(process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434");
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
    throw new Error("OLLAMA_BASE_URL must point to a local HTTP server.");
  }
  return { base: url.origin, model: process.env.JUNE_MODEL || "qwen3:0.6b" };
}

export async function getModelStatus(): Promise<ModelStatus> {
  const model = process.env.JUNE_MODEL || "qwen3:0.6b";
  try {
    const config = settings();
    const response = await fetch(`${config.base}/api/tags`, {
      signal: AbortSignal.timeout(5000), cache: "no-store",
    });
    if (!response.ok) throw new Error("The model server returned an error.");
    const data = await response.json();
    if (!Array.isArray(data.models)) throw new Error("The model list was not valid.");
    const installed = data.models.some((item: { name?: string }) => item.name === model);
    return installed
      ? { state: "ready", model, message: "Ready · runs on this Mac" }
      : { state: "missing", model, message: "Model missing. Run npm run model:pull, then reconnect." };
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.includes("OLLAMA_BASE_URL")) return { state: "error", model, message };
    return { state: "offline", model, message: "Ollama is offline. Start June’s model server, then reconnect." };
  }
}

// Adapters share this small interface, so the chat route doesn't depend on
// Ollama's wire format. A later phase can add another model here.
interface ModelAdapter {
  stream(messages: ChatMessage[], signal: AbortSignal): AsyncGenerator<ChatEvent>;
}

class OllamaAdapter implements ModelAdapter {
  async *stream(messages: ChatMessage[], signal: AbortSignal): AsyncGenerator<ChatEvent> {
    const { base, model } = settings();
    const response = await fetch(`${base}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.any([signal, AbortSignal.timeout(180000)]),
      body: JSON.stringify({
        model,
        messages: [{ role: "system", content: JUNE_PROMPT }, ...messages],
        stream: true,
        think: false,
        keep_alive: "5m",
        options: { num_ctx: 4096, num_predict: 256, temperature: 0.6 },
      }),
    });
    if (!response.ok || !response.body) {
      throw new Error(response.status === 404
        ? "Model missing. Run npm run model:pull, then reconnect."
        : "Ollama could not start this reply. Check the model server and try again.");
    }
    for await (const unknownChunk of readJsonLines(response.body)) {
      if (!unknownChunk || typeof unknownChunk !== "object") throw new Error("Ollama sent an invalid response.");
      const chunk = unknownChunk as { error?: string; done?: boolean; message?: { content?: string } };
      if (chunk.error) throw new Error("The model could not finish this reply. Start a new chat or reconnect.");
      if (typeof chunk.message?.content === "string" && chunk.message.content) {
        yield { type: "delta", text: chunk.message.content };
      }
      if (chunk.done === true) { yield { type: "done", model }; return; }
    }
    throw new Error("The model connection ended before the reply finished. Please try again.");
  }
}

class DemoAdapter implements ModelAdapter {
  async *stream(_messages: ChatMessage[], signal: AbortSignal): AsyncGenerator<ChatEvent> {
    const reply = "This is a simulated practice reply, not a model answer. The same chat flow will show real replies when you select Local AI and connect Ollama. I’m June — ready to grow one phase at a time.";
    for (const part of reply.match(/\S+\s*/g) || []) {
      signal.throwIfAborted();
      await new Promise<void>((resolve, reject) => {
        const abort = () => { clearTimeout(timer); reject(signal.reason); };
        const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 35);
        signal.addEventListener("abort", abort, { once: true });
      });
      yield { type: "delta", text: part };
    }
    yield { type: "done", model: "Simulated demo" };
  }
}

export function getAdapter(mode: ChatMode): ModelAdapter {
  return mode === "demo" ? new DemoAdapter() : new OllamaAdapter();
}
