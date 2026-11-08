import {proxyKnowledge} from "@/lib/server/knowledge";
export const runtime="nodejs";
export const dynamic="force-dynamic";
async function bridge(request:Request,context:{params:Promise<{path:string[]}>}){
  const {path}=await context.params;const route=path.join('/');
  const allowed=request.method==='GET' ? /^(status|documents(?:\/[\w-]{1,80})?)$/ : request.method==='DELETE' ? /^documents\/[\w-]{1,80}$/ : /^(documents|documents\/[\w-]{1,80}\/(retry|cancel))$/;
  if(!allowed.test(route))return Response.json({message:'Unknown document endpoint.'},{status:404});
  return proxyKnowledge(request,route);
}
export {bridge as GET,bridge as POST,bridge as DELETE};
