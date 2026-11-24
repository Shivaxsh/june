import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path?: string[]}> };
async function bridge(request: Request, context: Context) {
  const {path = []} = await context.params;
  const route = path.join("/");
  if (!(route === "" && ["GET", "POST"].includes(request.method)) && !(request.method === "POST" && /^(?:[\w-]{8,128}\/(?:cancel|acknowledge|claim|reschedule|snooze|skip)|series|series\/[\w-]{8,128}\/(?:update|pause|resume|cancel|skip-next))$/.test(route))) return Response.json({message:"Unknown June reminder endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({message:"Reminder endpoints accept no query arguments."},{status:400});
  return proxyBackend(request, `/api/reminders${route ? `/${route}` : ""}`, "library");
}
export {bridge as GET, bridge as POST};
