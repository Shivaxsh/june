# Local reminders

Say or type **Remind me at 6 PM to stretch**, **Remind me tomorrow at 18:30 to take a break**, **Remind me on 2026-11-20 at 6 PM to call home**, or **Remind me in ten minutes to rest**. June handles these locally without asking Qwen to invent or schedule a result.

Time can also follow the text: **Remind me to call home tomorrow at 6 PM**. June confirms the full calendar date, time and IANA time zone. The default is **Asia/Kolkata**, configurable with `JUNE_TIME_ZONE`. A clock time without a date uses its next occurrence, today or tomorrow. Explicitly past dates are rejected. An ambiguous **at 6** asks for AM or PM; a clear 24-hour time such as **18:30** is supported. Daylight-saving gaps and repeated wall times are rejected instead of guessed. Relative requests support the same clear durations as local timers, up to 24 hours.

Systems → Reminders accepts reminder text, a date and a local time, and displays June’s time zone. Reminders are one-shot, from now through the next 30 days, with at most 20 scheduled or undismissed reminders and text from 1 to 200 characters. **Show my reminders** lists scheduled reminders. **Cancel my reminder to stretch** cancels an exact text match; if several reminders match, use the specific Cancel button. Cancelling a due reminder dismisses it.

June stores absolute deadlines privately and checks them independently of model speed. Reloading preserves reminders; restarting June settles overdue reminders. June must be running for on-time completion, and spoken notices need the page open, voice enabled and output ready. This feature does not provide Mac notifications, background launch or a guarantee during sleep or shutdown.

Automatic notices use one persisted claim, so another tab or reload does not repeat them. Speech waits while June is busy. Old reminders first encountered after reopening stay visual after the freshness window; the card offers Hear again. A reminder dismissed before its queued alert plays is suppressed. Failed speech is not automatically replayed.

Data is in `reminders/reminders.sqlite3` under June's private data directory (0700 folder, 0600 database). Cancelled/dismissed history is pruned after seven days; undismissed due reminders stay until dismissed. Deleting a chat unlinks its reminder cards and does not cancel independently scheduled reminders. Request ids prevent duplicate creation, including repeated relative chat requests after their original deadline.

The same-origin API uses GET/POST `/api/reminders` and POST `/{id}/cancel`, `/acknowledge`, `/claim`. Create accepts only `text`, `localDate` (YYYY-MM-DD), `localTime` (HH:MM, optional seconds), optional IANA `timeZone`, and `requestId`; transitions require `{}`. Create bodies are bounded to 2 KiB. Clients cannot submit a command, path or override the scheduler's stored deadline directly.

See `docs/handoff.md` for actual automated and live checks.

## Edit and snooze

Scheduled and due reminders offer **Edit** for their date, time and text. Due cards also offer **Snooze 5 min**, **Snooze 10 min** and **Snooze 30 min**. Snoozing schedules the next occurrence from the time you press it. Cancelled or dismissed reminders stay closed; create a new reminder if needed.

Chat accepts **Move my stretch reminder to 7 PM**, **Move my stretch reminder to tomorrow at 7 PM**, **Snooze my stretch reminder for ten minutes**, and **Remind me again in ten minutes**. The last form needs exactly one due, undismissed reminder. Names match reminder text; if more than one matches, June asks which one. Ambiguous times and invalid durations do not change anything.

Every edit or snooze raises that reminder's schedule revision. A new revision clears its previous completion and announcement claim, and gets one new announcement opportunity at the new deadline. Old claims, buttons and queued alerts cannot consume a newer revision's claim. A newer record replaces an older one even when a due reminder becomes scheduled again. A sound already playing cannot be undone.

Edits are bound to the revision you opened. A conflicting change returns a refresh message rather than silently overwriting another change. Mutation request ids are retained for seven days: replaying an identical retained request returns the original result without moving the deadline again; a changed payload or stale revision is rejected. Saved edit/snooze chat turns reopen a card for the current reminder.

The API adds POST `/{id}/reschedule` with `revision`, `requestId`, `localDate`, `localTime`, optional `timeZone` and `text`; POST `/{id}/snooze` with `revision`, `requestId` and whole `seconds` from 1 to 86,400. Cancel, dismiss and claim send `{revision}`. The legacy empty body works only on revision 1, so an old page cannot accidentally affect a reminder that has since been edited.
