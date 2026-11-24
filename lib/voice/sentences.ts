// The completed chat keeps its labels and citations on screen.
export function spokenChatReply(reply: string) {
  const sourceHeading = "From your documents\n";
  // A general section after document evidence is introduced, not read as a label.
  const sections = (text: string) => text.replace(/\n\n(?:General knowledge|Document evidence)\n/g, "\n\nIn general:\n");
  if (reply.startsWith(sourceHeading)) {
    const body = reply.slice(sourceHeading.length);
    // A separate line lets the speech cleaner handle Markdown at the start
    // of the source body, including lists and headings.
    return `Your documents say:\n${sections(body)}`;
  }
  return sections(reply.replace(/^(?:Document evidence|General knowledge)\n/, ""));
}

// Re-evaluate the growing text, but emit each completed sentence only once.
// Keeping incomplete fences out of spoken text prevents a partial code block
// from being read aloud before its closing marker arrives.
export function spokenText(raw: string, preserveEnd = false) {
  // While streaming, a short unfinished link label at the very end can still
  // gain its destination. A stray "[" earlier never silences the rest.
  const stable = preserveEnd ? raw.replace(/!?\[[^\]\n]{0,120}(?:\](?:\([^)\s]*)?)?$/, "") : raw;
  const plain = stable.replace(/```[\s\S]*?(?:```|$)/g, " ")
    .replace(/~~~[\s\S]*?(?:~~~|$)/g, " ")
    .replace(/<\/?[a-z][^>\n]*>/gi, " ")
    .replace(/!?\[([^\]\n]+)\]\([^)]*\)/g, "$1")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/\s*\[\d{1,3}\]/g, "")
    // Tables: drop separator rows, read cells as a list.
    .replace(/(^|\n)\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{0,}:?\s*(?=\n|$)/g, "$1")
    .replace(/(^|\n)[ \t]*\|(.*?)\|?[ \t]*(?=\n|$)/g, (_, lead, cells) => lead + cells.split("|").map((cell: string) => cell.trim()).filter(Boolean).join(", "))
    .replace(/(^|\n)\s*(?:[-*_]\s*){3,}(?=\n|$)/g, "$1")
    .replace(/(^|\n)\s*(?:#{1,6}\s*|>\s*|[-*+•▪◦]\s+|\d+[.)]\s+)/g, "$1")
    // Emphasis markers go; identifiers (my_file) and maths (5 * 3) stay readable.
    .replace(/(\*\*|__)(?=\S)([^\n]*?\S)\1/g, "$2")
    .replace(/(^|[^\w*])\*(?=\S)([^*\n]*?\S)\*(?![\w*])/g, "$1$2")
    .replace(/(^|[^\w])_(?=\S)([^_\n]*?\S)_(?![\w])/g, "$1$2")
    .replace(/(\d)\s*\*\s*(\d)/g, "$1 times $2")
    .replace(/~~|[`*]/g, "")
    // A heading or list item without end punctuation gets a pause.
    .replace(/([^\s.!?:;,])[ \t]*\n(?=\s*\S)/g, "$1.\n")
    .replace(/\s+/g, " ");
  return preserveEnd ? plain.trimStart() : plain.trim();
}
export class SentenceBuffer {
  private raw = "";
  private emitted = 0;
  push(delta: string) { this.raw += delta; return this.units(false); }
  finish(completeOnly = false) { return this.units(true, completeOnly); }
  private units(final: boolean, completeOnly = false) {
    const text = spokenText(this.raw, true);
    const sentences: string[] = [];
    let start = 0;
    // A look-ahead space prevents splitting a decimal across network chunks.
    for (const match of text.matchAll(/[.!?]+["'”’)]*(?=\s|$)|[,;:—](?=\s)/g)) {
      const end = (match.index ?? 0) + match[0].length;
      if (!final && end === text.length) continue;
      // Short clauses sound clipped. Release only a stable, substantial clause.
      if (/^[,;:—]$/.test(match[0]) && end - start < 64) continue;
      if (/\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|e\.g|i\.e|U\.S)\.$/i.test(text.slice(start, end))) continue;
      const sentence = text.slice(start, end).trim(); if (sentence) sentences.push(sentence); start = end;
    }
    if (final && !completeOnly && text.slice(start).trim()) sentences.push(text.slice(start).trim());
    const ready = sentences.slice(this.emitted); this.emitted = sentences.length;
    return ready;
  }
}
export function mergeTranscript(draft: string, transcript: string) {
  const spoken = transcript.trim(); if (!spoken) return draft;
  return draft.trim() ? `${draft.trimEnd()}\n${spoken}` : spoken;
}
