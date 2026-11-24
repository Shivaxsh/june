# Repeating reminders

## Use them
- **In Systems → Reminders:** choose **Daily**, or **Weekly** and tap the days, then a start date, a time and what to remember.
- **In chat:**
  - **Create:** "Remind me every day at 11 PM to drink water", "Remind me every Monday and Thursday at 9 AM to stretch", "Remind me to read every weekday at 7:30 PM".
  - **Control:** "Pause / Resume / Stop my drink water reminder", "Skip the next drink water reminder".
  - **When unclear, June asks and sets nothing:** if the time could be AM or PM, if the purpose is missing, or if more than one reminder matches.

A repeating reminder keeps going until you stop it. Times are wall-clock times in the reminder's zone (Asia/Kolkata by default).

## What happens each day
- **Only due reminders exist.** The series stores its next date and time. A reminder appears only when it is due, and it is spoken once if this page is open and her voice is on.
- **A day's reminder can be:**
  - snoozed (never past the next regular time);
  - skipped (**Skip this time**);
  - dismissed.
  
  It can't be edited directly: edit the whole series instead. An edit never changes a reminder that is already due.
- **An undismissed reminder is replaced** when the next one comes due: it moves to history as *missed*.
- **Skip next** skips the upcoming day before it arrives.
- **Pause:**
  - nothing is said, including a reminder that is already due (it stays visible, silent);
  - a snoozed one is cancelled.
- **Resume** schedules the next future time. There is no catch-up.
- **Stop repeating** is final.

## When June was off or late
- A time noticed more than two minutes late (Mac asleep, June stopped) is **never spoken**.
- On startup, every overdue repeating reminder is archived quietly.
- The series shows one note, "Missed N times", and continues from the next future time. There is no burst of alerts.

## Clock changes
- A local time that doesn't exist that day (clocks jump forward) fires at the first valid minute on the same day, for example 02:30 → 03:00. It's marked "Moved for daylight saving".
- A time that happens twice uses the first one.

## Limits and storage
- **Up to 20 reminders at once.** Each active or paused repeating reminder counts as one, plus each unfinished one-time reminder. A paused one keeps its place, so Resume always works.
- **Storage:** repeating reminders are stored privately in `reminders/reminders.sqlite3`. Resolved days are removed 7 days after they were resolved, and stopped series 7 days after stopping.
- **Changes are idempotent:** every change is bound to the reminder's revision and stored as a receipt, so a retried request never applies twice and a stale one is refused.
- **Chat history:** deleting a chat removes its links only; it never stops a repeating reminder.

## API
- **`GET /api/reminders`** includes `series[]`. A day's reminder has `seriesId`, `occurrenceDate`, `outcome` (missed, skipped or paused) and `dstAdjusted`.
- **`POST /api/reminders/series`** creates a series.
- **`POST /api/reminders/series/{id}/{update|pause|resume|cancel}`** take `{revision, requestId}`.
- **`POST /api/reminders/series/{id}/skip-next`** takes `{revision, requestId, occurrenceDate}`.
- **`POST /api/reminders/{id}/skip`** takes `{revision, requestId}`.
- **One-time reminder routes and behaviour are unchanged.** Reschedule and cancel refuse a repeating reminder's day with guidance.
