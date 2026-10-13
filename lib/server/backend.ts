// Next.js is a small same-origin bridge. AI processing lives in Python.
type Kind = "chat" | "model-status" | "speech" | "speech-status" | "health";

export function backendURL() {
  const url = new URL(process.env.JUNE_BACKEND_URL || "http://127.0.0.1:8001");
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
    || url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("JUNE_BACKEND_URL must be a local HTTP origin.");
  }
  return url.origin;
}

function localRequest(request: Request) {
  try {
    const url = new URL(`http://${request.headers.get("host")}`);
    const origin = request.headers.get("origin");
    return ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
      && !url.username && !url.password && url.pathname === "/" && !url.search && !url.hash
      && (!origin || origin === url.origin);
  } catch { return false; }
}

function failure(kind: Kind, message: string, status = 503, code = "backend-offline") {
  const body = kind === "model-status"
    ? { state: "offline", model: process.env.JUNE_MODEL || "qwen2.5:1.5b", message }
    : kind === "speech-status" ? { state: "error", engine: "whisper.cpp", model: "base.en", message }
    : kind === "speech" ? { error: { code, message } }
    : kind === "health" ? { state: "offline", message }
    : { message };
  return Response.json(body, { status, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } });
}

export async function proxyBackend(request: Request, path: string, kind: Kind) {
  if (!localRequest(request)) return failure(kind, "Open June’s local page to use this service.", 403, "origin");
  const controller = new AbortController();
  const abort = () => controller.abort();
  request.signal.addEventListener("abort", abort, { once: true });
  if (request.signal.aborted) abort();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  const cleanup = () => { clearTimeout(timer); request.signal.removeEventListener("abort", abort); };
  try {
    let body: Uint8Array | undefined;
    if (request.method === "POST") {
      if (kind === "speech" && request.headers.get("content-type")?.split(";")[0].trim() !== "audio/wav") {
        cleanup(); return failure(kind, "Send a WAV recording from June’s listening controls.", 415, "format");
      }
      const limit = kind === "speech" ? 1048576 : 32000;
      const declared = request.headers.get("content-length");
      if (declared && (!/^\d+$/.test(declared) || Number(declared) > limit)) {
        cleanup(); return failure(kind, "The request is too large or has an invalid size.", kind === "speech" ? 413 : 400, "too-large");
      }
      if (!request.body) { cleanup(); return failure(kind, "No request body was received.", 400, "invalid-request"); }
      const input = request.body.getReader();
      const chunks: Uint8Array[] = []; let size = 0;
      try {
        while (true) {
          controller.signal.throwIfAborted();
          const part = await input.read();
          if (part.done) break;
          size += part.value.byteLength;
          if (size > limit) {
            await input.cancel(); cleanup();
            return failure(kind, "The request is too large. Shorten the message or recording.", kind === "speech" ? 413 : 400, "too-large");
          }
          chunks.push(part.value);
        }
      } finally { input.releaseLock(); }
      body = new Uint8Array(size); let offset = 0;
      for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
    }
    timer = setTimeout(abort, kind === "chat" ? 185000 : kind === "speech" ? 130000 : 8000);
    const upstream = await fetch(backendURL() + path, {
      method: request.method, body: body as BodyInit | undefined, cache: "no-store", signal: controller.signal, redirect: "error",
      headers: body ? { "Content-Type": kind === "speech" ? "audio/wav" : "application/json" } : undefined,
    });
    if (!upstream.body) throw new Error("Missing backend response");
    reader = upstream.body.getReader();
    // Pull-based forwarding avoids buffering the complete answer. Browser Stop
    // closes the Python request so it can release its model stream or process.
    const stream = new ReadableStream<Uint8Array>({
      async pull(output) {
        try {
          const next = await reader!.read();
          if (next.done) { cleanup(); reader!.releaseLock(); output.close(); }
          else output.enqueue(next.value);
        } catch (error) {
          cleanup(); controller.abort(); output.error(error);
        }
      },
      async cancel() {
        controller.abort(); cleanup();
        try { await reader!.cancel(); } catch { /* Fetch already closed after abort. */ }
      },
    });
    return new Response(stream, { status: upstream.status, headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store, no-transform", "X-Content-Type-Options": "nosniff",
    } });
  } catch {
    cleanup(); controller.abort();
    return failure(kind, request.signal.aborted ? "Request cancelled." : "June’s Python backend is unavailable. Restart June with npm start, then reconnect.",
      request.signal.aborted ? 499 : kind.endsWith("status") ? 200 : 503);
  }
}
