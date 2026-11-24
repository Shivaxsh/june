import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path?: string[]}> };
async function bridge(request: Request, context: Context) {
  const {path = []} = await context.params;
  const route = path.join("/");
  if (!(request.method === "GET" && route === "") && !(request.method === "POST" && /^(propose|run|preferences|projects|projects\/[\w-]{8,128}\/(remove|forget)|[\w-]{8,128}\/(approve|cancel))$/.test(route))) return Response.json({message:"Unknown June action endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({message:"Action endpoints accept no query arguments."},{status:400});
  return proxyBackend(request, `/api/actions${route ? `/${route}` : ""}`, "library");
}
export {bridge as GET, bridge as POST};
