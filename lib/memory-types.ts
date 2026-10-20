export const characterFields = ["who", "values", "speech", "humour", "quirks", "taste", "never", "address", "mood", "growth"] as const;
export type CharacterField = typeof characterFields[number];
export type Expression = "steady" | "calm" | "bright";
export type Profile = {fields: Record<CharacterField, string>; expression: Expression};
export type Memory = {id: string; text: string; pinned: boolean | number; source: string | null};
export type Suggestion = {id: string; conversation: string; turn: string; text: string; quote: string};
export type SavedTurn = {id: string; user: string; assistant: string; status: "pending" | "complete" | "stopped" | "failed"; memories: string};
export type ConversationSummary = {id: string; title: string; updated: number};
export type SavedConversation = ConversationSummary & {turns: SavedTurn[]};
export type LibraryState = {revision: number; retentionDays: number; memories: Memory[]; suggestions: Suggestion[]; conversations: ConversationSummary[]; profile: Profile};
export type ImportPreview = {memories: Pick<Memory,"text"|"pinned">[]; profile: Profile | null; conversations: {title: string; turns: unknown[]}[]};
export const expressionRates: Record<Expression, number> = {steady: .98, calm: .92, bright: 1.04};

export class LibraryError extends Error { constructor(message:string, readonly status:number){super(message);} }

export async function libraryRequest<T>(path: string, method = "GET", value?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/library/${path}`, {method, cache:"no-store", signal,
    ...(value === undefined ? {} : {headers:{"Content-Type":"application/json"}, body:JSON.stringify(value)})});
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new LibraryError(typeof data?.message === "string" ? data.message : "June’s private storage is unavailable. Retry or explicitly choose temporary chat.", response.status);
  return data as T;
}
