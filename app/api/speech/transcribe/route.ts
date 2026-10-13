import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export function POST(request: Request) { return proxyBackend(request, "/api/speech/transcribe", "speech"); }
