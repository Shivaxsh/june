export default function ReplyStatus({ state, hasContent, limited, incomplete, repetitionStopped, busy, onRetry, onContinue, temporary }: {
  state?: 'pending' | 'complete' | 'stopped' | 'failed'; hasContent?: boolean; limited?: boolean; incomplete?: boolean;
  repetitionStopped?: boolean; busy: boolean; onRetry(): void;
  /** Present only for the latest saved partial reply, where a structured continuation is possible. */
  onContinue?: () => void; temporary?: boolean;
}) {
  // An unclosed fence shows a cut; closed fences say nothing about whether the program works.
  const partial = state === 'complete' && !repetitionStopped && (limited || incomplete);
  const more = onContinue ? <button className="quiet-button" disabled={busy} onClick={onContinue}>Continue</button>
    : temporary ? <> · temporary chat: type “continue” to ask for more</> : null;
  return <>
    {state === 'stopped' && hasContent && <span className="message-note">Stopped · partial reply</span>}
    {repetitionStopped && <span className="message-note">Repetition stopped · text preserved <button className="quiet-button" disabled={busy} onClick={onRetry}>Retry reply</button></span>}
    {partial && <span className="message-note is-partial" role="note">{limited ? 'Cut off at the length limit' : 'Code block may be unfinished'}{more}</span>}
    {state === 'failed' && <span className="message-note">Not completed · your typed draft is preserved</span>}
  </>;
}
