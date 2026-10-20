import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path: string[]}> };
async function bridge(request: Request, context: Context) {
  const {path} = await context.params;
  const route = path.join("/");
  if (!/^(state|conversations(?:\/[\w-]{1,80})?|memories(?:\/[\w-]{1,80})?|suggestions\/[\w-]{1,80}|personality|export|import(?:\/preview)?|cancel|extract)$/.test(route)) return Response.json({message:"Unknown June data endpoint."}, {status:404});
  return proxyBackend(request, `/api/library/${route}${new URL(request.url).search}`, "library");
}
export {bridge as GET, bridge as POST, bridge as PUT, bridge as PATCH, bridge as DELETE};
