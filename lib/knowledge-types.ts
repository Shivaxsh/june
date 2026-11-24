export type SelectedScope = {documentIds: string[]};
export type KnowledgeScope = SelectedScope | {mode: "auto"};
export const libraryScope = {mode: "auto"} as const;
export const provenances = ["documents", "general", "mixed", "missing", "mixed-missing", "memory"] as const;
export type Provenance = typeof provenances[number];
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
  if (!scope || typeof scope !== "object") return null;
  if ("mode" in scope && scope.mode === "auto") return libraryScope;
  return "documentIds" in scope && Array.isArray(scope.documentIds) && scope.documentIds.length > 0 && scope.documentIds.every(id=>typeof id === 'string' && !!id) ? {documentIds:[...new Set(scope.documentIds)]} : null;
}
export function validateCitations(value:unknown, scope?:SelectedScope):Citation[] {
  if (!Array.isArray(value)) throw new Error("June did not confirm document citations.");
  const position=(n:unknown)=> n===null || (Number.isInteger(n) && (n as number)>0);
  if (!value.every(c=>c && typeof c.documentId==='string' && (!scope || scope.documentIds.includes(c.documentId)) && typeof c.chunkId==='string' && !!c.chunkId && typeof c.name==='string' && typeof c.quote==='string' && !!c.quote.trim() && position(c.page) && position(c.lineStart) && position(c.lineEnd) && (c.lineStart===null || c.lineEnd===null || c.lineEnd>=c.lineStart))) throw new Error("June returned invalid document citations. Retry the question.");
  return value as Citation[];
}
export function validatedDocumentReply(reply:string, event:{citations?:unknown;knowledgeRevision?:unknown;memoryIds?:unknown;provenance?:unknown;continuedFrom?:unknown}, scope:KnowledgeScope) {
  // Approved facts may inform a saved-memory answer or a general answer, never a document answer.
  const fromMemory = "mode" in scope && (event.provenance === "memory" || event.provenance === "general");
  if (!Number.isInteger(event.knowledgeRevision) || (event.knowledgeRevision as number)<0 ||
      (event.memoryIds !== undefined && (!Array.isArray(event.memoryIds) || !event.memoryIds.every(id => typeof id === "string" && !!id) || (!fromMemory && event.memoryIds.length)))) throw new Error("June did not validate the reply sources.");
  const text=reply.trim();
  // A server-verified continuation suffix of a general or memory reply is a fragment: it may
  // begin with the closing fence or a bracket of code started earlier. It still carries no citations.
  const continuation = "mode" in scope && typeof event.continuedFrom === "string" && event.continuedFrom.length > 0
    && (event.provenance === "general" || event.provenance === "memory");
  // A general or memory reply may open with fenced code. A json fence is a transport envelope
  // only when it is empty or carries the model's answer fields; document replies stay strict.
  const conversational = "mode" in scope && (event.provenance === "general" || event.provenance === "memory");
  const envelopeFence = /^```\s*json\b/i.test(text) && (/^```\s*json\s*(?:[\[{]\s*[\]}]\s*)?(?:```)?$/i.test(text)
    || /"(?:answer|citations|documentStatus|documentAnswer|generalAnswer|supported|chunkId)"\s*:/.test(text));
  const fenced = conversational ? envelopeFence : /^```/.test(text);
  // A serialized model envelope must never enter playback or saved display text.
  if (!text || (!continuation && (/^[\[{]/.test(text) || fenced))) throw new Error("June returned an unvalidated document answer. Retry the question.");
  // The server labels document sections itself; the body after that app-owned label must be prose,
  // never serialized JSON or a fence (live: documentAnswer was the citations array as a string).
  // General sections keep their own rules, so a mixed reply's general part may still open with code.
  for (const section of text.matchAll(/(?:^|\n\n)(?:From your documents|Document evidence)\n([\s\S]*?)(?=\n\n(?:From your documents|Document evidence|General knowledge)\n|$)/g))
    if (!section[1].trim() || /^\s*(?:[\[{]|```|~~~)/.test(section[1])) throw new Error("June returned an unvalidated document answer. Retry the question.");
  // A labelled general section beside a document finding comes from the same model envelope:
  // it may show code, but never the envelope's own fields.
  for (const section of text.matchAll(/(?:^|\n\n)General knowledge\n([\s\S]*?)(?=\n\n(?:From your documents|Document evidence|General knowledge)\n|$)/g))
    if (/^\s*(?:[\[{]|```\s*json\b)/i.test(section[1]) && /"(?:answer|citations|documentStatus|documentAnswer|generalAnswer|supported|chunkId)"\s*:/.test(section[1]))
      throw new Error("June returned an unvalidated document answer. Retry the question.");
  const citations = validateCitations(event.citations, "documentIds" in scope ? scope : undefined);
  if ("mode" in scope) {
    const provenance = event.provenance as Provenance;
    const requiresSources = provenance === "documents" || provenance === "mixed";
    if (!provenances.includes(provenance) || requiresSources !== (citations.length > 0)) throw new Error("June did not confirm where the reply came from. Retry the question.");
  }
  return citations;
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
