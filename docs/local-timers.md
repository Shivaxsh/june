# Local timers and remembered VS Code approval

## Timers

Say or type **Set a timer for 10 minutes**, **Set a timer for one minute and thirty seconds**, or **Set a timer for 2 minutes called tea**. **Cancel my timer**, **Cancel tea timer**, and **How much time is left on my timer?** are handled by the local application, without model inference. If several timers match, June asks which one instead of cancelling a guess.

**Systems → Timers** has duration/name controls, countdowns, Cancel, Hear again and Dismiss. Durations run from one second to 24 hours, with at most 20 active or undismissed timers. A timer can be cancelled by its specific card. Countdown display uses the server's clock; only the server marks it finished.

The backend scheduler persists deadlines and status, independently of Qwen. Reloading keeps timers. When June restarts, overdue timers become finished. This is not a Mac notification service: alerts need June's page open, Speak replies enabled and the local voice ready. Mac sleep or a stopped June server cannot produce a real-time alert.

Finished timers wait until June is free to speak, without cancelling a reply or recording. One persisted claim lets at most one tab attempt the automatic announcement. Dismissing a timer suppresses its queued alert. Timers witnessed running in this page can announce after a long reply; old completed timers first seen on opening the page remain visual after the freshness window. Hear again explicitly replays a finished timer's notice if needed.

Timer labels and deadlines are stored privately in `timers/timers.sqlite3` under June's data directory (0700 directory, 0600 database). Cancelled and dismissed history is pruned after seven days. Undismissed finished timers count toward the limit. Deleting a chat removes its timer links but does not cancel an independent timer.

Create requests carry a unique request id, so an immediate retry returns the same timer. Claim, cancel and dismiss transitions are transactional. Timer routes accept at most 1 KiB and no client-controlled deadline, command or file path.

## Remember approval for the same action

Approval cards remain. The fixed VS Code card has **Remember this approval for opening VS Code**, checked by default at the user's request. If it is still ticked when you click **Approve**, approval is saved for exactly opening Visual Studio Code or bringing it forward. It accepts no files, arguments or shell commands. Other actions never show this option and never become trusted.

After a genuine approval is remembered, a direct **Open VS Code** request returns an observed outcome without asking again. The request is still journaled before execution and replayed request ids do not launch it twice while retained. In **Systems → Hands**, switching off **Remember approval for opening VS Code** restores review for future requests. When it is off, the switch reads **Review every time** and cannot be turned back on from Hands; remembering again needs another approval with the box ticked. Turning trust on through settings requires a completed, previously approved VS Code action in the ledger.

The user's existing VS Code approval is eligible to be remembered under their explicit instruction. No broader permission is inferred. Qwen 4B and its parameters remain unchanged.

See `docs/handoff.md` for exact checks and live verification results.
