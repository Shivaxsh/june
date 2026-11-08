import {backendURL} from "./backend";
const LIMIT=10*1024*1024;
const failure=(message:string,status:number)=>Response.json({message},{status,headers:{"Cache-Control":"no-store"}});
export async function proxyKnowledge(request:Request,path:string) {
  const host=request.headers.get("host");
  const origin=request.headers.get("origin");
  try {
    const local=new URL(`http://${host}`);
    if (!["localhost","127.0.0.1","[::1]"].includes(local.hostname) || local.host!==host || (origin && origin!==local.origin)) return failure("Open June’s local page to use documents.",403);
  } catch {return failure("Invalid local origin.",403);}
  const upload=request.method==='POST' && path==='documents';
  const controller=new AbortController();
  const abort=()=>controller.abort();
  request.signal.addEventListener('abort',abort,{once:true});
  if(request.signal.aborted)abort();
  const timer=setTimeout(abort,35000);
  try {
    let body:Uint8Array|undefined;
    const headers:Record<string,string>={};
    if(upload){
      if(request.headers.get('content-type')?.split(';')[0].trim()!=='application/octet-stream') return failure('Upload raw document bytes.',415);
      const name=request.headers.get('x-file-name');
      if(!name || name.length>2048) return failure('A file name is required.',400);
      try {if(!decodeURIComponent(name).trim())throw new Error();} catch {return failure('Invalid file name.',400);}
      const declared=request.headers.get('content-length');
      if(declared && (!/^\d+$/.test(declared)||Number(declared)>LIMIT))return failure('Documents must be at most 10 MiB.',413);
      if(!request.body)return failure('Choose a document to upload.',400);
      const reader=request.body.getReader();const chunks:Uint8Array[]=[];let size=0;
      const cancelInput=()=>{void reader.cancel().catch(()=>{});};
      controller.signal.addEventListener('abort',cancelInput,{once:true});
      try {while(true){controller.signal.throwIfAborted();const part=await reader.read();if(part.done)break;size+=part.value.byteLength;if(size>LIMIT){await reader.cancel();return failure('Documents must be at most 10 MiB.',413);}chunks.push(part.value);}}
      finally {controller.signal.removeEventListener('abort',cancelInput);reader.releaseLock();}
      body=new Uint8Array(size);let offset=0;for(const chunk of chunks){body.set(chunk,offset);offset+=chunk.byteLength;}
      headers['Content-Type']='application/octet-stream';headers['X-File-Name']=name;
    }
    const response=await fetch(`${backendURL()}/api/knowledge/${path}`,{method:request.method,body:body as BodyInit|undefined,headers,cache:'no-store',redirect:'error',signal:controller.signal});
    const data=await response.arrayBuffer();
    return new Response(data,{status:response.status,headers:{'Content-Type':response.headers.get('content-type')||'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
  }catch{return failure(request.signal.aborted?'Request cancelled.':'June’s document service is unavailable.',request.signal.aborted?499:503);}
  finally{clearTimeout(timer);request.signal.removeEventListener('abort',abort);}
}
