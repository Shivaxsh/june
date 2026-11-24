import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path?: string[]}> };
async function bridge(request: Request, context: Context) {
  const {path = []} = await context.params;
  const route = path.join("/");
  const read = request.method === "GET" && (route === "" || /^[a-f0-9]{32}$/.test(route));
  const write = request.method === "POST" && (route === "" || route === "forget" || /^[a-f0-9]{32}\/(approve|cancel|voice-approve)$/.test(route));
  if (!read && !write) return Response.json({code:"invalid-plan",message:"Unknown workflow endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({code:"invalid-plan",message:"No query arguments are supported."},{status:400});
  return proxyBackend(request, `/api/plans${route ? `/${route}` : ""}`, "library");
}
export {bridge as GET, bridge as POST};
