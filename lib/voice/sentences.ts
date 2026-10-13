// Re-evaluate the growing text, but emit each completed sentence only once.
// Keeping incomplete fences out of spoken text prevents a partial code block
// from being read aloud before its closing marker arrives.
export function spokenText(raw: string, preserveEnd = false) {
  const plain = raw.replace(/```[\s\S]*?(?:```|$)/g, " ")
    .replace(/~~~[\s\S]*?(?:~~~|$)/g, " ")
    .replace(/!?\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/(^|\n)\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)/g, "$1")
    .replace(/[`*_~]/g, "").replace(/\s+/g, " ");
  return preserveEnd ? plain.trimStart() : plain.trim();
}
export class SentenceBuffer {
  private raw = "";
  private emitted = 0;
  push(delta: string) { this.raw += delta; return this.units(false); }
  finish() { return this.units(true); }
  private units(final: boolean) {
    const text = spokenText(this.raw, true);
    const sentences: string[] = [];
    let start = 0;
    // A look-ahead space prevents splitting a decimal across network chunks.
    for (const match of text.matchAll(/[.!?]+["'”’)]*(?=\s)/g)) {
      const end = (match.index ?? 0) + match[0].length;
      if (/\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|e\.g|i\.e|U\.S)\.$/i.test(text.slice(start, end))) continue;
      const sentence = text.slice(start, end).trim(); if (sentence) sentences.push(sentence); start = end;
    }
    if (final && text.slice(start).trim()) sentences.push(text.slice(start).trim());
    const ready = sentences.slice(this.emitted); this.emitted = sentences.length;
    return ready;
  }
}
export function mergeTranscript(draft: string, transcript: string) {
  const spoken = transcript.trim(); if (!spoken) return draft;
  return draft.trim() ? `${draft.trimEnd()}\n${spoken}` : spoken;
}
