/* A deterministic force layout for June's knowledge constellation. Real data
 * only: ready documents, approved memories and saved chats, linked by stored
 * citations and memory sources. It contains ids and short labels, never text. */

export type GraphNodeType = "doc" | "mem" | "chat";
export type GraphNode = { id: string; type: GraphNodeType; label: string; x: number; y: number };
export type GraphEdge = { a: number; b: number; type: "cite" | "mem" };
export type GraphLinks = { citations: { conversation: string; documentId: string }[]; memories: { id: string; source: string | null }[] };
export type GraphInput = {
  documents: { id: string; name: string; status: string }[];
  memories: { id: string; source: string | null }[];
  conversations: { id: string; title: string }[];
  links: GraphLinks | null;
};

/** At most this many nodes of each type are drawn, which bounds the O(n²) layout. */
export const NODE_CAP = 60;

export function trimLabel(value: string, limit = 18) {
  const clean = value.replace(/\s+/g, " ").trim();
  return clean.length > limit ? clean.slice(0, limit - 1) + "…" : clean;
}

export function buildConstellation(input: GraphInput, iterations = 220) {
  let seed = 11;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const nodes: GraphNode[] = [];
  const index = new Map<string, number>();
  const add = (id: string, type: GraphNodeType, label: string, spread: number) => {
    index.set(type + ":" + id, nodes.length);
    nodes.push({ id, type, label, x: rnd() * spread * 2 - spread, y: rnd() * spread * 2 - spread });
  };
  const ready = input.documents.filter(d => d.status === "ready");
  ready.slice(0, NODE_CAP).forEach(d => add(d.id, "doc", trimLabel(d.name), 100));
  input.memories.slice(0, NODE_CAP).forEach(m => add(m.id, "mem", "", 120));
  input.conversations.slice(0, NODE_CAP).forEach(c => add(c.id, "chat", trimLabel(c.title), 120));
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();
  const link = (a: number | undefined, b: number | undefined, type: GraphEdge["type"]) => {
    if (a === undefined || b === undefined) return;
    const key = a + "-" + b; if (seen.has(key)) return; seen.add(key); edges.push({ a, b, type });
  };
  input.links?.citations.forEach(c => link(index.get("chat:" + c.conversation), index.get("doc:" + c.documentId), "cite"));
  (input.links?.memories ?? input.memories).forEach(m => { if (m.source) link(index.get("mem:" + m.id), index.get("chat:" + m.source), "mem"); });
  for (let it = 0; it < iterations; it++) {
    for (let a = 0; a < nodes.length; a++) for (let b = a + 1; b < nodes.length; b++) {
      const A = nodes[a], B = nodes[b]; let dx = A.x - B.x, dy = A.y - B.y;
      // Documents carry labels, so they push each other further apart.
      const d = Math.max(6, Math.hypot(dx, dy)), f = (A.type === "doc" && B.type === "doc" ? 1400 : 260) / (d * d); dx /= d; dy /= d;
      A.x += dx * f; A.y += dy * f; B.x -= dx * f; B.y -= dy * f;
    }
    for (const { a, b } of edges) {
      const A = nodes[a], B = nodes[b], dx = B.x - A.x, dy = B.y - A.y, d = Math.hypot(dx, dy) || 1, f = (d - 42) * .02;
      A.x += dx / d * f; A.y += dy / d * f; B.x -= dx / d * f; B.y -= dy / d * f;
    }
    for (const n of nodes) { n.x *= .992; n.y *= .992; }
  }
  // counts are what is drawn; totals are what exists, so the legend can say "60 of 75".
  const counts = {
    documents: nodes.filter(n => n.type === "doc").length,
    memories: nodes.filter(n => n.type === "mem").length,
    chats: nodes.filter(n => n.type === "chat").length,
    citations: edges.filter(e => e.type === "cite").length,
  };
  const totals = {
    documents: ready.length,
    memories: input.memories.length,
    chats: input.conversations.length,
    citations: input.links?.citations.length ?? 0,
  };
  return { nodes, edges, counts, totals };
}
