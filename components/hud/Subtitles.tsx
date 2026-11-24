"use client";

export type SubtitleWord = { key: number; text: string; state: "done" | "now" | "todo" };

/** Split spoken text into words with their place relative to the voice's current range [start, end). Spaces stay
 * attached to the preceding word, so the sentence wraps and reads naturally. */
export function subtitleWords(text: string, start: number, end: number): SubtitleWord[] {
  const words: SubtitleWord[] = [];
  for (const match of text.matchAll(/\S+\s*/g)) {
    const a = match.index ?? 0, b = a + match[0].length;
    const state = b <= start ? "done" : a < Math.max(end, start + 1) && b > start ? "now" : "todo";
    words.push({ key: a, text: match[0], state });
  }
  return words;
}

/** Subtitles: while June speaks, words condense out of blur in step with her voice; otherwise a quiet line
 * (the latest reply, your question while she works, or how to start). */
export default function Subtitles({ caption, start, end, fallback, quiet }: { caption: string; start: number; end: number; fallback: string; quiet: boolean }) {
  if (!caption) return <p className={`june-subtitle${quiet ? " is-quiet" : ""}`} aria-hidden="true">{fallback}</p>;
  return <p className="june-subtitle" aria-hidden="true">
    {subtitleWords(caption, start, end).map(word => <span key={word.key} className={`june-word is-${word.state}`}>{word.text}</span>)}
  </p>;
}
