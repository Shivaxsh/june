import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path: string[]}> };
export async function POST(request: Request, context: Context) {
  const {path} = await context.params;
  const route = path.join("/");
  if (!/^((open-meteo|apple-music|apple-calendar)\/(enable|disable)|google\/(configure|authorize|revoke))$/.test(route)) return Response.json({code:"invalid-assistant",message:"Unknown connection endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({code:"invalid-assistant",message:"No query arguments are supported."},{status:400});
  return proxyBackend(request, `/api/connections/${route}`, "library");
}
