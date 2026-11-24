import { proxyBackend } from "@/lib/server/backend";
export const runtime = "nodejs";
type Context = { params: Promise<{path?: string[]}> };
// Simulated commerce (docs/commerce-contract.md): read drafts/receipts, prepare or update a draft, arm a spoken review.
// Approval never goes through here: it uses the plans API with the exact reviewed fingerprint.
async function bridge(request: Request, context: Context) {
  const {path = []} = await context.params;
  const route = path.join("/");
  const read = request.method === "GET" && (route === "" || /^[A-Za-z0-9_-]{1,80}$/.test(route));
  const write = request.method === "POST" && (route === "respond" || /^[A-Za-z0-9_-]{1,80}\/arm$/.test(route));
  if (!read && !write) return Response.json({code:"invalid-transaction",message:"Unknown booking endpoint."},{status:404});
  if (new URL(request.url).search) return Response.json({code:"invalid-transaction",message:"No query arguments are supported."},{status:400});
  return proxyBackend(request, `/api/transactions${route ? `/${route}` : ""}`, "library");
}
export {bridge as GET, bridge as POST};
