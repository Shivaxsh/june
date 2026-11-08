export type KnowledgeScope = {documentIds: string[]};
export type Citation = {documentId:string;chunkId:string;name:string;page:number|null;lineStart:number|null;lineEnd:number|null;quote:string;deleted?:boolean};
export type KnowledgeDocument = {id:string;name:string;status:string;message:string;progress:number;pages:number;warning?:string};
export type Passage = {id:string;text:string;page:number|null;lineStart:number|null;lineEnd:number|null};
export type DocumentPreview = KnowledgeDocument & {passages:Passage[]};
export const DOCUMENT_LIMIT = 10 * 1024 * 1024;
export function parseStored<T>(value: T | string | undefined, fallback:T):T {
  if (value === undefined || value === null) return fallback;
  try { return typeof value === "string" ? JSON.parse(value) : value; } catch { return fallback; }
}
export function parseScope(value:unknown):KnowledgeScope|null {
  const scope=parseStored(value,null) as KnowledgeScope|null;
  return scope && Array.isArray(scope.documentIds) && scope.documentIds.length > 0 && scope.documentIds.every(id=>typeof id === 'string' && !!id) ? {documentIds:[...new Set(scope.documentIds)]} : null;
}
export function validateCitations(value:unknown, scope?:KnowledgeScope):Citation[] {
  if (!Array.isArray(value)) throw new Error("June did not confirm document citations.");
  const position=(n:unknown)=> n===null || (Number.isInteger(n) && (n as number)>0);
  if (!value.every(c=>c && typeof c.documentId==='string' && (!scope || scope.documentIds.includes(c.documentId)) && typeof c.chunkId==='string' && !!c.chunkId && typeof c.name==='string' && typeof c.quote==='string' && !!c.quote.trim() && position(c.page) && position(c.lineStart) && position(c.lineEnd) && (c.lineStart===null || c.lineEnd===null || c.lineEnd>=c.lineStart))) throw new Error("June returned invalid document citations. Retry the question.");
  return value as Citation[];
}
export function validatedDocumentReply(reply:string, event:{citations?:unknown;knowledgeRevision?:unknown;memoryIds?:unknown}, scope:KnowledgeScope) {
  if (!Number.isInteger(event.knowledgeRevision) || (event.knowledgeRevision as number)<0 || (Array.isArray(event.memoryIds) && event.memoryIds.length)) throw new Error("June did not validate the document reply.");
  const text=reply.trim();
  // A serialized model envelope must never enter playback or saved display text.
  if (!text || /^[\[{]/.test(text) || /^```(?:json)?/i.test(text)) throw new Error("June returned an unvalidated document answer. Retry the question.");
  return validateCitations(event.citations,scope);
}
export async function knowledgeRequest<T>(path:string, method="GET", body?:File, signal?:AbortSignal):Promise<T> {
  const response=await fetch(`/api/knowledge/${path}`,{method,cache:"no-store",signal,...(body ? {body,headers:{"Content-Type":"application/octet-stream","X-File-Name":encodeURIComponent(body.name)}} : {})});
  const data=await response.json().catch(()=>null);
  if (!response.ok) throw new Error(typeof data?.message==='string'?data.message:"Documents are unavailable. Try again.");
  return data as T;
}

export function supportingPassage(document:DocumentPreview,citation:Citation):Passage {
  const passage=document.passages?.find(p=>p.id===citation.chunkId);
  if(document.id!==citation.documentId || !passage || !passage.text.includes(citation.quote)) throw new Error("The supporting passage is no longer available. Refresh Documents.");
  return passage;
}
