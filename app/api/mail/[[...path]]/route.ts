import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path?: string[]}> };
async function bridge(request: Request, context: Context) {
  const {path = []} = await context.params;
  const route = path.join("/");
  const read = request.method === "GET" && route === "";
  const write = request.method === "POST" && (route === "enable" || /^receipts\/[a-f0-9]{32}\/check$/.test(route));
  if (!read && !write) return Response.json({code:"invalid-mail",message:"Unknown email endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({code:"invalid-mail",message:"No query arguments are supported."},{status:400});
  return proxyBackend(request, `/api/mail${route ? `/${route}` : ""}`, route.startsWith("receipts/") ? "long" : "library");
}
export {bridge as GET, bridge as POST};
