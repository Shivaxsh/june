import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path: string[]}> };
async function bridge(request: Request, context: Context) {
  const {path} = await context.params;
  const route = path.join("/");
  const read = request.method === "GET" && /^(settings|goals|music\/playlists|today)$/.test(route);
  const write = request.method === "POST" && /^(settings|goals|weather\/places|briefing|goals\/[a-f0-9]{32}\/(update|complete|reopen|delete))$/.test(route);
  if (!read && !write) return Response.json({code:"invalid-assistant",message:"Unknown Daily endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({code:"invalid-assistant",message:"No query arguments are supported."},{status:400});
  return proxyBackend(request, `/api/assistant/${route}`, "library");
}
export {bridge as GET, bridge as POST};
