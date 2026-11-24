"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { countsLine, proposePlan, type Plan } from "@/lib/integrations";
import { allowJobs, allowMail, checkJob, checkReceipt, findJobs, finishedApplications, forgetAnswer, newestReplies, teachAnswer, getJobs, getMail, jobSettings, skipJob, type Job, type JobsState, type MailReceipt, type MailState } from "@/lib/mail";

type Props = { plans: Plan[]; onPlan: (plan: Plan, serverNow: number) => void; onAnnounce: (text: string) => void };
const MAIL_PROBLEM_WORDS: Record<NonNullable<MailState["problem"]>, string> = {
  "disk-access": "June can’t read Mail’s index right now: “June Mail” needs Full Disk Access again (System Settings → Privacy & Security → Full Disk Access; remove the old JuneMail entry, then add it again).",
  "automation-permission": "macOS is blocking June Mail from using Mail. Allow it in System Settings → Privacy & Security → Automation.",
  unavailable: "Mail didn’t answer just now. Check that the Mail app works, then reopen this panel.",
};
const JOBS_PROBLEM_WORDS: Record<NonNullable<JobsState["problem"]>, string> = {
  "automation-permission": "macOS is blocking June Browser from using Chrome. Allow it in System Settings → Privacy & Security → Automation.",
  "javascript-off": "Chrome’s “Allow JavaScript from Apple Events” is off. In Chrome: View → Developer → tick it.",
  unavailable: "Chrome didn’t answer just now. Check Chrome, then try again.",
};
const RECEIPT_WORDS: Record<MailReceipt["status"], string> = { pending: "Send outcome not confirmed yet", verified: "Verified in Sent", "not-sent": "Not sent" };
const STATUS_WORDS: Record<Job["status"], string> = { found: "", applied: "Applied · confirmed by Naukri", "needs-you": "Needs you", "not-confirmed": "Not confirmed", skipped: "Skipped", replied: "Reply received" };

/** Email through the Mail app and Naukri jobs through your Chrome. Sending and applying always show a card first. */
export default function MailJobsPanel({ plans, onPlan, onAnnounce }: Props) {
  const [mail, setMail] = useState<MailState | null>(null);
  const [jobs, setJobs] = useState<JobsState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"" | "mail" | "jobs" | "find" | "receipt" | "refresh">("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [last, setLast] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const inFlight = useRef(false);
  const alive = useRef(true);

  // Jobs replies are ordered: an older request finishing late never overwrites a newer list.
  const jobsReplies = useRef(newestReplies());
  const updateJobs = useCallback(async <T extends JobsState | { jobs: JobsState }>(request: Promise<T>) => {
    const token = jobsReplies.current.begin();
    const reply = await request;
    if (alive.current && jobsReplies.current.take(token)) setJobs("jobs" in reply && !("enabled" in reply) ? reply.jobs : reply as JobsState);
    return reply;
  }, []);
  const load = useCallback(async () => {
    const [m, j] = await Promise.allSettled([getMail(), updateJobs(getJobs())]);
    if (!alive.current) return;
    if (m.status === "fulfilled") setMail(m.value);
    setError(m.status === "rejected" && j.status === "rejected" ? "Email and jobs are unavailable." : "");
  }, [updateJobs]);
  useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; }; }, [load]);
  const shown = last ? plans.find(p => p.id === last) : undefined;
  // Any job application that finishes (from this panel, June's chat, another tab or after a reload) refreshes the jobs
  // list — jobs only, never Mail. Applications already finished when the panel opened are covered by its first load.
  const refreshJobs = useCallback(() => updateJobs(getJobs()).catch(() => undefined), [updateJobs]);
  const seenApplications = useRef<Set<string> | null>(null);
  useEffect(() => {
    const first = seenApplications.current === null;
    if (first) seenApplications.current = new Set();
    if (finishedApplications(seenApplications.current!, plans, first)) void refreshJobs();
  }, [plans, refreshJobs]);

  async function guarded(kind: "mail" | "jobs" | "find" | "receipt" | "refresh", work: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(kind); setError("");
    try { await work(); }
    catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : "June could not do that."); }
    finally { inFlight.current = false; if (alive.current) setBusy(""); }
  }
  const apply = (ids: string[]) => guarded("jobs", async () => {
    const reply = await proposePlan("job-apply", undefined, undefined, { ids });
    onPlan(reply.plan, reply.serverNow); setLast(reply.plan.id); setChosen([]);
    onAnnounce(`${ids.length === 1 ? "An application is" : `${ids.length} applications are`} ready for your review.`);
  });
  const toggle = (id: string) => setChosen(now => now.includes(id) ? now.filter(x => x !== id) : now.length >= 5 ? now : [...now, id]);
  const note = !shown ? "" : shown.status === "proposed" ? "Review the card under “Waiting for review” above."
    : shown.status === "approved" || shown.status === "running" ? "Applying in Chrome… June pauses between jobs and checks Naukri’s confirmation."
    : [countsLine(shown), ...shown.steps.map(step => step.result?.message)].filter(Boolean).join(" · ");
  const open = (jobs?.jobs ?? []).filter(j => j.status === "found" || j.status === "not-confirmed");
  const done = (jobs?.jobs ?? []).filter(j => j.status !== "found" && j.status !== "not-confirmed" && j.status !== "skipped");

  return <section className="timers-panel integrations-panel" aria-label="Email and jobs">
    <div className="integration-group" aria-label="Email">
      <h3>Email</h3>
      <p className="handsfree-note">June uses the accounts in your Mail app. Ask “check my email”, “read the latest email from Rahul”, or “reply to Rahul saying I’ll join at 5”. Every email she writes is shown on a card and is sent only if you approve that exact email. Email text is treated as information, never as instructions.</p>
      {mail && !mail.installed && <p className="error-notice">The June Mail helper isn’t installed yet.</p>}
      {mail && <div className="plan-actions">
        {mail.enabled && mail.problem && <><p className="error-notice" role="alert">{MAIL_PROBLEM_WORDS[mail.problem]}</p>
          <div className="timer-buttons"><button type="button" className="quiet-button" disabled={!!busy}
            onClick={() => void guarded("refresh", async () => { const next = await getMail(); if (alive.current) setMail(next); onAnnounce(next.problem ? "Mail still isn’t working." : "Mail is working again."); })}>
            {busy === "refresh" ? "Checking Mail…" : "Refresh Mail status"}</button></div></>}
        <p className="plan-step-meta">{mail.enabled && mail.problem ? "Mail: allowed, but not working right now." : mail.enabled ? `Mail: allowed${mail.accounts.length ? ` · ${mail.accounts.join(", ")}` : ""}${mail.unread !== null ? ` · ${mail.unread} unread` : ""}` : "Mail: not allowed. June can’t read or send email."}</p>
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={!!busy || !mail.installed}
          onClick={() => void guarded("mail", async () => { const next = await allowMail(!mail.enabled); if (alive.current) setMail(next); onAnnounce(next.enabled ? "June can now read your email when you ask." : "June will no longer read or send email."); })}>
          {busy === "mail" ? "Waiting for macOS…" : mail.enabled ? "Stop email access" : "Allow Mail"}</button></div>
        {!mail.enabled && <p className="handsfree-note">When you click Allow Mail, macOS asks whether “June Mail” may control Mail. Click OK.</p>}
      </div>}
      {mail && mail.receipts.length > 0 && <>
        <p className="plan-step-meta">Email send checks</p>
        {(!mail.enabled || mail.problem) && mail.receipts.some(r => r.status === "pending") && <p className="handsfree-note">To check Sent again, June needs working Mail access{mail.enabled ? ": see the note above." : ": click Allow Mail above."}</p>}
        <ul className="command-list" aria-label="Sent email receipts">{mail.receipts.map(r => <li key={r.id}>
          <div><strong>{r.subject}</strong> <span className={`job-status receipt-${r.status}`}>{RECEIPT_WORDS[r.status]}</span>
            <span className="plan-step-meta">To {r.to.join(", ")} · {new Date(r.at).toLocaleString([], { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</span>
            {r.status === "pending" && <span className="plan-step-meta">Mail may still be saving it to Sent. Checking again only looks; it never sends the email again.</span>}</div>
          {r.status === "pending" && <div className="timer-buttons"><button type="button" className="quiet-button" disabled={!!busy || !mail.enabled || !!mail.problem}
            onClick={() => void guarded("receipt", async () => { const next = await checkReceipt(r.id); if (alive.current) setMail(next);
              const now = next.receipts.find(x => x.id === r.id); onAnnounce(now ? `${r.subject}: ${RECEIPT_WORDS[now.status]}.` : "Checked Sent."); })}>
            {busy === "receipt" ? "Checking Sent…" : "Check Sent again"}</button></div>}
        </li>)}</ul>
      </>}
      {mail?.enabled && mail.recent.length > 0 && <ul className="command-list">{mail.recent.map((m, i) => <li key={i}>
        <div><strong>{m.name}</strong>{m.unread && <span className="plan-step-meta"> · unread</span>}<span className="mail-subject">{m.subject}</span></div></li>)}</ul>}
    </div>

    <div className="integration-group" aria-label="Naukri jobs">
      <h3>Naukri jobs</h3>
      <p className="handsfree-note">June reads your Naukri recommendations in Chrome (and Naukri alert emails), sorts them by how many words in the job title also appear in the resume in Documents, and applies only to the jobs you approve on a card. A job counts as applied only when Naukri’s own page confirms it. If the recruiter asks questions, June answers them from your saved answers and submits. A question she has never seen stops that application and appears below for you to answer once; she remembers it. A log-in, captcha, OTP, test or the company’s own site always stops her and leaves the page open for you.</p>
      <p className="handsfree-note">Naukri’s rules don’t allow automated applying, so your account could be restricted. Keep the daily limit low.</p>
      {jobs && !jobs.installed && <p className="error-notice">The June Browser helper isn’t installed yet.</p>}
      {jobs && <div className="plan-actions">
        {jobs.enabled && jobs.problem && <p className="error-notice" role="alert">{JOBS_PROBLEM_WORDS[jobs.problem]}</p>}
        <p className="plan-step-meta">{jobs.enabled && jobs.problem ? "Chrome: allowed, but not working right now." : jobs.enabled ? `Chrome: allowed · ${jobs.appliedToday} of ${jobs.dailyLimit} applications today${jobs.stopped ? " · applying stopped" : ""}` : "Chrome: not allowed."}</p>
        <div className="timer-buttons">
          <button type="button" className="quiet-button" disabled={!!busy || !jobs.installed}
            onClick={() => void guarded("jobs", async () => { const next = await updateJobs(allowJobs(!jobs.enabled)); onAnnounce(next.enabled ? "June can now use Chrome for Naukri." : "June will no longer use Chrome."); })}>
            {jobs.enabled ? "Stop Chrome access" : "Allow Chrome"}</button>
          {jobs.enabled && <button type="button" className="quiet-button" disabled={!!busy}
            onClick={() => void guarded("find", async () => { const next = await updateJobs(findJobs()); onAnnounce("Jobs updated."); })}>{busy === "find" ? "Finding and ranking… (a minute or two)" : "Find jobs"}</button>}
          {jobs.enabled && <button type="button" className="quiet-button" disabled={!!busy}
            onClick={() => void guarded("jobs", async () => { const next = await updateJobs(jobSettings({ stopped: !jobs.stopped })); onAnnounce(next.stopped ? "Applying is stopped." : "Applying is allowed again."); })}>{jobs.stopped ? "Allow applying" : "Stop applying"}</button>}
        </div>
        {jobs.enabled && <label className="command-field">Applications per day
          <select value={jobs.dailyLimit} disabled={!!busy} onChange={event => void guarded("jobs", async () => { await updateJobs(jobSettings({ dailyLimit: Number(event.target.value) })); })}>
            {[3, 5, 10, 15, 25].map(n => <option key={n} value={n}>{n}</option>)}</select></label>}
        {!jobs.enabled && <p className="handsfree-note">Before allowing: in Chrome, open the View menu → Developer → tick “Allow JavaScript from Apple Events”, and make sure you’re logged in to Naukri. Then click Allow Chrome and click OK when macOS asks.</p>}
      </div>}
      {open.length > 0 && <>
        <p className="handsfree-note">“% title keywords” only counts words from the job title that also appear in your resume. It isn’t a judgement of fit: read the full role and your resume before approving.</p>
        <ul className="command-list job-list">{open.map(job => <li key={job.id}>
          <label className="job-pick"><input type="checkbox" checked={chosen.includes(job.id)} disabled={!chosen.includes(job.id) && chosen.length >= 5} onChange={() => toggle(job.id)} />
            <span><strong>{job.title}</strong>{job.company && <> · {job.company}</>}
              <span className="plan-step-meta">{[job.location, job.experience, job.salary].filter(Boolean).join(" · ")}{job.status === "not-confirmed" ? " · not confirmed last time" : ""}</span>
              {job.score !== null && <span className="job-fit">{job.score}% title keywords{job.reason ? ` · ${job.reason}` : ""}</span>}</span></label>
          <div className="timer-buttons"><button type="button" className="quiet-button" disabled={!!busy} onClick={() => void guarded("jobs", async () => { await updateJobs(skipJob(job.id)); })}>Skip</button></div>
        </li>)}</ul>
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={!!busy || chosen.length === 0 || jobs?.stopped} onClick={() => void apply(chosen)}>
          {chosen.length ? `Review ${chosen.length} application${chosen.length === 1 ? "" : "s"}` : "Choose up to 5 jobs"}</button></div>
      </>}
      {note && <p className="quick-result" role="status">{note}</p>}
      {done.length > 0 && <ul className="command-list">{done.map(job => <li key={job.id}>
        <div><strong>{job.title}</strong>{job.company && <> · {job.company}</>} <span className={`job-status job-${job.status}`}>{STATUS_WORDS[job.status]}</span>
          {job.detail && job.status !== "applied" && <span className="plan-step-meta">{job.detail}</span>}</div>
        {job.status === "needs-you" && <div className="timer-buttons"><button type="button" className="quiet-button" disabled={!!busy || !jobs?.enabled}
          onClick={() => void guarded("jobs", async () => { const next = await updateJobs(checkJob(job.id)); onAnnounce(next.message); })}>
          Check Naukri again</button></div>}</li>)}</ul>}
      {jobs && <div className="integration-group" aria-label="Recruiter answers">
        <p className="plan-step-meta">Recruiter answers</p>
        {!jobs.standing && <p className="handsfree-note">Your standing answers aren’t set up yet, so June will ask you about each question the first time.</p>}
        {jobs.questions.length > 0 && <ul className="command-list" aria-label="Questions waiting for your answer">{jobs.questions.map(q => <li key={q.key}>
          <div><strong>{q.question}</strong></div>
          {q.options.length > 0
            ? <div className="timer-buttons">{q.options.map(option => <button key={option} type="button" className="quiet-button" disabled={!!busy}
                onClick={() => void guarded("jobs", async () => { await updateJobs(teachAnswer(q.question, option)); onAnnounce(`Saved. June will answer “${option}” from now on.`); })}>{option}</button>)}</div>
            : <div className="timer-buttons"><input type="text" maxLength={300} aria-label={`Your answer to: ${q.question}`} value={drafts[q.key] ?? ""}
                onChange={e => { const value = e.target.value; setDrafts(now => ({ ...now, [q.key]: value })); }} />
              <button type="button" className="quiet-button" disabled={!!busy || !(drafts[q.key] ?? "").trim()}
                onClick={() => void guarded("jobs", async () => { await updateJobs(teachAnswer(q.question, drafts[q.key] ?? "")); if (alive.current) { setDrafts(now => { const { [q.key]: _, ...rest } = now; return rest; }); } onAnnounce("Saved. June will use this answer from now on."); })}>Save answer</button></div>}
        </li>)}</ul>}
        {jobs.questions.length > 0 && <p className="handsfree-note">After answering, approve the job again and June will finish it with your new answer.</p>}
        {jobs.answers.length > 0 && <details><summary>Answers you taught June ({jobs.answers.length})</summary>
          <ul className="command-list">{jobs.answers.map(a => <li key={a.key}><div><strong>{a.question}</strong> <span className="plan-step-meta">{a.answer}</span></div>
            <div className="timer-buttons"><button type="button" className="quiet-button" disabled={!!busy}
              onClick={() => void guarded("jobs", async () => { await updateJobs(forgetAnswer(a.key)); onAnnounce("Forgotten. June will ask you next time."); })}>Forget</button></div></li>)}</ul></details>}
      </div>}
      {done.some(job => job.status === "needs-you") && <p className="handsfree-note">Finished one yourself on Naukri? “Check Naukri again” only reads the job page: it never clicks, and counts the job as applied only if Naukri shows it applied.</p>}
    </div>
    {error && <p className="error-notice" role="alert">{error}</p>}
  </section>;
}
