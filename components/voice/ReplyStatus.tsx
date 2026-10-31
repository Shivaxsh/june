export default function ReplyStatus({ state, hasContent, limited, repetitionStopped, busy, onRetry }: {
  state?: 'pending' | 'complete' | 'stopped' | 'failed'; hasContent?: boolean; limited?: boolean;
  repetitionStopped?: boolean; busy: boolean; onRetry(): void;
}) {
  return <>
    {state === 'stopped' && hasContent && <span className="message-note">Stopped · partial reply</span>}
    {repetitionStopped && <span className="message-note">Repetition stopped · text preserved <button className="quiet-button" disabled={busy} onClick={onRetry}>Retry reply</button></span>}
    {limited && <span className="message-note">Reply length limit reached · ask June to continue</span>}
    {state === 'failed' && <span className="message-note">Not completed · your typed draft is preserved</span>}
  </>;
}
