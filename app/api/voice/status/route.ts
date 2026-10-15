import { backendURL, proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const response = await proxyBackend(request, "/api/voice/status", "health");
  try {
    const result = await response.json();
    return Response.json({ ...result, websocketUrl: backendURL().replace(/^http:/, "ws:") + "/ws/voice" },
      { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ state: "error", message: "Hands-free status is unavailable. Restart June and refresh." },
      { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
