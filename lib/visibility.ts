// The embedded desktop browser can report "hidden" for a few milliseconds
// during layout. Media and microphone release on a real tab switch, not on
// that flicker: act only if the page is still hidden after a short grace.
export const HIDDEN_GRACE_MS = 500;
export function onSustainedHide(action: () => void, doc: Pick<Document, "hidden" | "addEventListener" | "removeEventListener"> = document, wait: (fn: () => void, ms: number) => unknown = (fn, ms) => setTimeout(fn, ms), clear: (id: unknown) => void = id => clearTimeout(id as ReturnType<typeof setTimeout>)) {
  let timer: unknown;
  const changed = () => { clear(timer); if (doc.hidden) timer = wait(() => { if (doc.hidden) action(); }, HIDDEN_GRACE_MS); };
  doc.addEventListener("visibilitychange", changed);
  return () => { clear(timer); doc.removeEventListener("visibilitychange", changed); };
}
