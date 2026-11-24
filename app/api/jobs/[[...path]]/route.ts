import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path?: string[]}> };
async function bridge(request: Request, context: Context) {
  const {path = []} = await context.params;
  const route = path.join("/");
  const read = request.method === "GET" && route === "";
  const write = request.method === "POST" && (route === "enable" || route === "find" || route === "settings" || route === "answers" || route === "answers/forget" || /^\d{8,16}\/(?:skip|check)$/.test(route));
  if (!read && !write) return Response.json({code:"invalid-jobs",message:"Unknown jobs endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({code:"invalid-jobs",message:"No query arguments are supported."},{status:400});
  return proxyBackend(request, `/api/jobs${route ? `/${route}` : ""}`, route === "find" || route.endsWith("/check") ? "long" : "library");
}
export {bridge as GET, bridge as POST};
