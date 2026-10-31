import { JUNE_VERSION } from "@/lib/version";
import { backendURL, proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  try {
    const response = await proxyBackend(request, "/health", "health");
    const data = await response.json();
    if (response.ok && data?.service === "june-python" && data?.version === JUNE_VERSION) {
      return Response.json({ ...data, websocketUrl: backendURL().replace(/^http:/, "ws:") + "/ws/chat" }, { headers: { "Cache-Control": "no-store" } });
    }
    return Response.json({ state: "offline", message: data?.message || "June’s Python backend is unavailable. Restart June." }, { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ state: "offline", message: "June’s Python backend returned an invalid health check. Restart June." }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
