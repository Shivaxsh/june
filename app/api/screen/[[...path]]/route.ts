import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path?: string[]}> };
// Only the on/off switch and its status: the screen itself is read only from a chat request.
async function bridge(request: Request, context: Context) {
  const {path = []} = await context.params;
  const route = path.join("/");
  const read = request.method === "GET" && route === "";
  const write = request.method === "POST" && route === "enable";
  if (!read && !write) return Response.json({code:"invalid-screen",message:"Unknown screen endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({code:"invalid-screen",message:"No query arguments are supported."},{status:400});
  return proxyBackend(request, `/api/screen${route ? `/${route}` : ""}`, "library");
}
export {bridge as GET, bridge as POST};
