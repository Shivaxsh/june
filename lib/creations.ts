// Documents June made (Word, PowerPoint, PDF). Names only: file paths stay on the server.
import { call, defaultHttp, IntegrationError, type Http } from "./integrations";

export type CreationKind = "docx" | "pptx" | "pdf" | "site";
export type Creation = { id: string; kind: CreationKind; title: string; fileName: string; createdAt: number; exists: boolean; url: string | null; design: string | null };
export type CreationState = { folder: string; creations: Creation[] };
const URL = /^https:\/\/[a-z0-9](?:[a-z0-9-]{0,38})\.github\.io\/[a-z0-9]+(?:-[a-z0-9]+)*\/$/;
export const KIND_WORDS: Record<CreationKind, string> = { docx: "Word document", pptx: "Presentation", pdf: "PDF", site: "Website" };

const ID = /^[a-f0-9]{32}$/;
const invalid = () => new IntegrationError("June returned her documents in an unexpected form.", 502, "invalid-response");
const text = (value: unknown, max: number): value is string => typeof value === "string" && value.trim().length > 0 && value.length <= max;

function parseState(data: Record<string, unknown>): CreationState {
  const { folder, creations } = data;
  if (!text(folder, 120) || !Array.isArray(creations) || creations.length > 50) throw invalid();
  return { folder, creations: creations.map(value => {
    const c = value as Creation;
    if (!c || typeof c !== "object" || !ID.test(c.id) || !["docx", "pptx", "pdf", "site"].includes(c.kind) || !text(c.title, 120) || !text(c.fileName, 140) || /[\\/]/.test(c.fileName)
      || typeof c.createdAt !== "number" || !Number.isFinite(c.createdAt) || typeof c.exists !== "boolean"
      || (c.url !== null && c.url !== undefined && (typeof c.url !== "string" || !URL.test(c.url)))
      || (c.design !== null && c.design !== undefined && !text(c.design, 80))) throw invalid();
    return { id: c.id, kind: c.kind, title: c.title, fileName: c.fileName, createdAt: c.createdAt, exists: c.exists, url: c.url ?? null, design: c.design ?? null };
  }) };
}
export async function getCreations(http: Http = defaultHttp) { return parseState(await call(http, "/api/creations")); }
export async function openCreation(id: string, how: "open" | "reveal", http: Http = defaultHttp) {
  if (!ID.test(id) || (how !== "open" && how !== "reveal")) throw new IntegrationError("June cannot open that document.", 400, "invalid-input");
  return parseState(await call(http, `/api/creations/${id}/${how}`, {}));
}
