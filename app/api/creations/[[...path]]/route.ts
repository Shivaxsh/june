import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path?: string[]}> };
async function bridge(request: Request, context: Context) {
  const {path = []} = await context.params;
  const route = path.join("/");
  const read = request.method === "GET" && route === "";
  const write = request.method === "POST" && /^[a-f0-9]{32}\/(open|reveal)$/.test(route);
  if (!read && !write) return Response.json({code:"invalid-creation",message:"Unknown documents endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({code:"invalid-creation",message:"No query arguments are supported."},{status:400});
  return proxyBackend(request, `/api/creations${route ? `/${route}` : ""}`, "library");
}
export {bridge as GET, bridge as POST};
