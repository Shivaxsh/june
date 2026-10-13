import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export function GET(request: Request) { return proxyBackend(request, "/api/status", "model-status"); }
