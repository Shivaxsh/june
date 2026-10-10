import { MAX_CONTEXT_LENGTH, MAX_CONTEXT_MESSAGES, MAX_MESSAGE_LENGTH } from "@/lib/chat-types";
import type { ChatMessage, ChatMode, ChatEvent } from "@/lib/chat-types";
import { getAdapter, getModelStatus } from "@/lib/server/model";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  // Reject cross-origin browser requests; this personal server is local only.
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  let allowed = false;
  try {
    const local = new URL(`http://${host}`);
    // Next.js normalizes request.url to localhost internally. The browser's
    // Host header retains the real address (127.0.0.1), so compare against it.
    allowed = ["127.0.0.1", "localhost", "[::1]"].includes(local.hostname)
      && (!origin || origin === local.origin);
  } catch { /* A malformed host is rejected below. */ }
  if (!allowed) {
    return Response.json({ message: "Use June’s local page to send messages." }, { status: 403 });
  }
  let input: unknown;
  try {
    if (Number(request.headers.get("content-length")) > 32000) throw new Error();
    const text = await request.text();
    if (text.length > 32000) throw new Error();
    input = JSON.parse(text);
  } catch {
    return Response.json({ message: "The message request was not valid JSON or was too large." }, { status: 400 });
  }
  const data = input as { mode?: unknown; messages?: unknown } | null;
  const mode: ChatMode = data?.mode === undefined ? "local" : data.mode as ChatMode;
  if (!data || !["local", "demo"].includes(mode) || !Array.isArray(data.messages) || !data.messages.length || data.messages.length > MAX_CONTEXT_MESSAGES) {
    return Response.json({ message: "Please send a valid conversation. Start a new chat if this one is too long." }, { status: 400 });
  }
  const valid = data.messages.every((item, i) => item && typeof item === "object"
    && item.role === (i % 2 === 0 ? "user" : "assistant")
    && typeof item.content === "string" && item.content.trim().length > 0
    && item.content.length <= MAX_MESSAGE_LENGTH);
  if (!valid || data.messages.at(-1).role !== "user") {
    return Response.json({ message: "Each message needs valid text and a user or assistant role." }, { status: 400 });
  }
  const messages = data.messages as ChatMessage[];
  if (messages.reduce((sum, item) => sum + item.content.length, 0) > MAX_CONTEXT_LENGTH) {
    return Response.json({ message: "This conversation is getting long for June’s small model. Start a new chat to continue." }, { status: 400 });
  }
  if (mode === "local") {
    const status = await getModelStatus();
    if (status.state !== "ready") return Response.json({ message: status.message }, { status: 503 });
  }
  const controller = new AbortController();
  const cancel = () => controller.abort();
  request.signal.addEventListener("abort", cancel, { once: true });
  if (request.signal.aborted) cancel();
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(output) {
      const send = (event: ChatEvent) => output.enqueue(encoder.encode(JSON.stringify(event) + "\n"));
      try {
        for await (const event of getAdapter(mode).stream(messages, controller.signal)) {
          if (controller.signal.aborted) break;
          send(event);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const detail = error instanceof Error && error.name === "TimeoutError"
            ? "June took too long to reply. Try a shorter message or reconnect."
            : error instanceof TypeError ? "The model server disconnected. Restart Ollama, then reconnect."
            : error instanceof Error ? error.message : "June could not finish this reply. Try again.";
          send({ type: "error", message: detail });
        }
      } finally {
        request.signal.removeEventListener("abort", cancel);
        if (!controller.signal.aborted) output.close();
      }
    },
    cancel,
  });
  return new Response(stream, { headers: {
    "Content-Type": "application/x-ndjson; charset=utf-8",
    "Cache-Control": "no-store, no-transform",
    "X-Content-Type-Options": "nosniff",
  } });
}
