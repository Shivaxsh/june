import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// macOS shows its own password prompt; the person may take a while to answer it.
export const maxDuration = 180;
export async function POST(request: Request) { return proxyBackend(request, "/api/voice/repair", "voice"); }
