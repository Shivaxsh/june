import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path?: string[]}> };
async function bridge(request: Request, context: Context) {
  const {path = []} = await context.params;
  const route = path.join("/");
  if (!(route === "" && ["GET", "POST"].includes(request.method)) && !(request.method === "POST" && /^[\w-]{8,128}\/(cancel|acknowledge|claim)$/.test(route))) return Response.json({message:"Unknown June timer endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({message:"Timer endpoints accept no query arguments."},{status:400});
  return proxyBackend(request, `/api/timers${route ? `/${route}` : ""}`, "library");
}
export {bridge as GET, bridge as POST};
