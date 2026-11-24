import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
export async function GET(request: Request) {
  if (new URL(request.url).search) return Response.json({code:"invalid-plan",message:"No query arguments are supported."},{status:400});
  return proxyBackend(request, "/api/capabilities", "library");
}
