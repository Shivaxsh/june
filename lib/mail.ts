// Email (Mail app) and Naukri jobs. Sending and applying are always plans (lib/integrations).
import { call, defaultHttp, IntegrationError, type Http } from "./integrations";

export type MailRow = { name: string; subject: string; date: string; unread: boolean };
/** Why an allowed tool cannot work right now, as the backend found it on this request (null when it works). */
export type MailProblem = "disk-access" | "automation-permission" | "unavailable";
export type JobsProblem = "automation-permission" | "javascript-off" | "unavailable";
/** One email June sent after approval, and what Mail's Sent folder shows about it. No body is ever included. */
export type ReceiptStatus = "pending" | "verified" | "not-sent";
export type MailReceipt = { id: string; to: string[]; subject: string; status: ReceiptStatus; at: number };
export type MailState = { enabled: boolean; installed: boolean; accounts: string[]; unread: number | null; recent: MailRow[]; problem: MailProblem | null; receipts: MailReceipt[] };
const RECEIPT_STATUS: ReceiptStatus[] = ["pending", "verified", "not-sent"];
const ADDRESS = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}$/;
function parseReceipts(value: unknown): MailReceipt[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > 20) throw invalid();
  return value.map(item => {
    const v = item as MailReceipt;
    if (!v || typeof v !== "object" || !/^[a-f0-9]{32}$/.test(v.id) || !Array.isArray(v.to) || v.to.length < 1 || v.to.length > 10
      || !v.to.every(a => typeof a === "string" && a.length <= 254 && ADDRESS.test(a)) || !text(v.subject, 300, false) || !RECEIPT_STATUS.includes(v.status)
      || typeof v.at !== "number" || !Number.isFinite(v.at)) throw invalid();
    return { id: v.id, to: [...v.to], subject: v.subject, status: v.status, at: v.at };
  });
}
export type JobStatus = "found" | "applied" | "needs-you" | "not-confirmed" | "skipped" | "replied";
export type Job = { id: string; title: string; company: string; location: string; experience: string; salary: string; score: number | null; reason: string; status: JobStatus; detail: string; at: number };
/** A recruiter question June met with no saved answer; she asks once and remembers the answer. */
export type JobQuestion = { key: string; question: string; options: string[]; job: string; title: string; waitingUntil: number | null };
/** An answer the person taught June (their standing answers file stays private on the Mac and is not listed). */
export type SavedAnswer = { key: string; question: string; answer: string };
export type JobsState = { enabled: boolean; installed: boolean; dailyLimit: number; appliedToday: number; stopped: boolean; jobs: Job[]; problem: JobsProblem | null;
  questions: JobQuestion[]; answers: SavedAnswer[]; standing: boolean };
const MAIL_PROBLEMS: MailProblem[] = ["disk-access", "automation-permission", "unavailable"];
const JOBS_PROBLEMS: JobsProblem[] = ["automation-permission", "javascript-off", "unavailable"];
// Absent means the backend did not check; any other unknown value is a malformed reply.
function problem<T extends string>(value: unknown, known: T[]): T | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string" || !known.includes(value as T)) throw invalid();
  return value as T;
}

const invalid = () => new IntegrationError("June returned email or jobs in an unexpected form.", 502, "invalid-response");
const text = (value: unknown, max: number, empty = true): value is string => typeof value === "string" && value.length <= max && (empty || value.trim().length > 0);
const STATUS: JobStatus[] = ["found", "applied", "needs-you", "not-confirmed", "skipped", "replied"];

function parseMail(data: Record<string, unknown>): MailState {
  const { enabled, installed, accounts, unread, recent } = data;
  const issue = problem(data.problem, MAIL_PROBLEMS);
  const receipts = parseReceipts(data.receipts);
  if (typeof enabled !== "boolean" || typeof installed !== "boolean" || !Array.isArray(accounts) || accounts.length > 20 || !accounts.every(a => text(a, 100))
    || (unread !== null && (typeof unread !== "number" || !Number.isInteger(unread) || unread < 0)) || !Array.isArray(recent) || recent.length > 30) throw invalid();
  return { enabled, installed, problem: issue, receipts, accounts: accounts as string[], unread: unread as number | null, recent: recent.map(r => {
    const v = r as MailRow;
    if (!v || typeof v !== "object" || !text(v.name, 300) || !text(v.subject, 300) || !text(v.date, 40) || typeof v.unread !== "boolean") throw invalid();
    return { name: v.name, subject: v.subject, date: v.date, unread: v.unread };
  }) };
}

function parseJobs(data: Record<string, unknown>): JobsState {
  const { enabled, installed, dailyLimit, appliedToday, stopped, jobs } = data;
  const questions = data.questions === undefined ? [] : data.questions, answers = data.answers === undefined ? [] : data.answers;
  if (!Array.isArray(questions) || questions.length > 20 || !Array.isArray(answers) || answers.length > 100) throw invalid();
  const parsedQuestions = questions.map(q => {
    const v = q as JobQuestion;
    if (!v || typeof v !== "object" || !text(v.key, 300, false) || !text(v.question, 300, false) || !Array.isArray(v.options) || v.options.length > 12
      || !v.options.every(o => text(o, 120, false)) || !/^\d{8,16}$/.test(v.job)) throw invalid();
    const title = v.title === undefined ? "" : v.title, waitingUntil = v.waitingUntil === undefined ? null : v.waitingUntil;
    if (!text(title, 200) || !(waitingUntil === null || (typeof waitingUntil === "number" && Number.isFinite(waitingUntil)))) throw invalid();
    return { key: v.key, question: v.question, options: [...v.options], job: v.job, title, waitingUntil };
  });
  const parsedAnswers = answers.map(a => {
    const v = a as SavedAnswer;
    if (!v || typeof v !== "object" || !text(v.key, 300, false) || !text(v.question, 300, false) || !text(v.answer, 300, false)) throw invalid();
    return { key: v.key, question: v.question, answer: v.answer };
  });
  const standing = data.standing === undefined ? false : data.standing;
  if (typeof standing !== "boolean") throw invalid();
  const issue = problem(data.problem, JOBS_PROBLEMS);
  if (typeof enabled !== "boolean" || typeof installed !== "boolean" || typeof stopped !== "boolean" || !Number.isInteger(dailyLimit) || !Number.isInteger(appliedToday)
    || !Array.isArray(jobs) || jobs.length > 40) throw invalid();
  return { enabled, installed, stopped, problem: issue, questions: parsedQuestions, answers: parsedAnswers, standing, dailyLimit: dailyLimit as number, appliedToday: appliedToday as number, jobs: jobs.map(j => {
    const v = j as Job;
    if (!v || typeof v !== "object" || !/^\d{8,16}$/.test(v.id) || !text(v.title, 200, false) || !text(v.company, 200) || !text(v.location, 120) || !text(v.experience, 60)
      || !text(v.salary, 60) || !(v.score === null || (Number.isInteger(v.score) && v.score >= 0 && v.score <= 100)) || !text(v.reason, 140) || !STATUS.includes(v.status)
      || !text(v.detail, 300) || typeof v.at !== "number") throw invalid();
    return { id: v.id, title: v.title, company: v.company, location: v.location, experience: v.experience, salary: v.salary, score: v.score, reason: v.reason, status: v.status, detail: v.detail, at: v.at };
  }) };
}

export async function getMail(http: Http = defaultHttp) { return parseMail(await call(http, "/api/mail")); }
export async function allowMail(allowed: boolean, http: Http = defaultHttp) { return parseMail(await call(http, "/api/mail/enable", { allowed })); }
/** Look in Sent again for one email June already sent. Read-only: it never sends anything. */
export async function checkReceipt(id: string, http: Http = defaultHttp) {
  if (!/^[a-f0-9]{32}$/.test(id)) throw new IntegrationError("June cannot check that email.", 400, "invalid-input");
  return parseMail(await call(http, `/api/mail/receipts/${id}/check`, {}));
}
export async function getJobs(http: Http = defaultHttp) { return parseJobs(await call(http, "/api/jobs")); }
export async function allowJobs(allowed: boolean, http: Http = defaultHttp) { return parseJobs(await call(http, "/api/jobs/enable", { allowed })); }
export async function findJobs(http: Http = defaultHttp) { return parseJobs(await call(http, "/api/jobs/find", {})); }
export async function jobSettings(value: { dailyLimit?: number; stopped?: boolean }, http: Http = defaultHttp) {
  if (value.dailyLimit !== undefined && (!Number.isInteger(value.dailyLimit) || value.dailyLimit < 1 || value.dailyLimit > 25)) throw new IntegrationError("Choose a daily limit from 1 to 25.", 400, "invalid-input");
  return parseJobs(await call(http, "/api/jobs/settings", value));
}
/** Your answer to a recruiter question; June types it automatically whenever Naukri asks it again. */
export async function teachAnswer(question: string, answer: string, http: Http = defaultHttp) {
  const clean = answer.trim();
  // One line: June Browser types answers into Naukri's single-line boxes and refuses control characters.
  if (!question || question.length > 300 || !clean || clean.length > 300 || /[\x00-\x1f\x7f]/.test(clean)) throw new IntegrationError("Write an answer of up to 300 characters.", 400, "invalid-input");
  return parseJobs(await call(http, "/api/jobs/answers", { question, answer: clean }));
}
export async function forgetAnswer(key: string, http: Http = defaultHttp) {
  if (!key || key.length > 300) throw new IntegrationError("Choose a saved answer.", 400, "invalid-input");
  return parseJobs(await call(http, "/api/jobs/answers/forget", { key }));
}
/** After you finished an application yourself: June looks at the job page again (read-only, never clicks) and
 * records it as applied only if Naukri shows it applied. */
export async function checkJob(id: string, http: Http = defaultHttp) {
  if (!/^\d{8,16}$/.test(id)) throw new IntegrationError("June cannot check that job.", 400, "invalid-input");
  const data = await call(http, `/api/jobs/${id}/check`, {});
  const message = data.message;
  if (typeof message !== "string" || message.length > 1000) throw invalid();  // names the job: title and company can be long
  return { jobs: parseJobs(data), message };
}
export async function skipJob(id: string, http: Http = defaultHttp) {
  if (!/^\d{8,16}$/.test(id)) throw new IntegrationError("June cannot skip that job.", 400, "invalid-input");
  return parseJobs(await call(http, `/api/jobs/${id}/skip`, {}));
}

/** The live-question card's rules. Each wait is its own instance (question + job + waiting time); answers are still
 * saved by question. A refresh that started before any answer is ignored, always (a permanent, monotonic barrier).
 * An answered instance stays hidden for `hold` ms while June picks it up (shown again if still waiting after that:
 * she re-asked). Every new instance is announced once; instances past their waiting time are never shown. */
export function liveQuestions({ hold = 10000 }: { hold?: number } = {}) {
  let seq = 0, floor = 0, sending = "";
  const id = (q: JobQuestion) => `${q.key}\u0000${q.job}\u0000${q.waitingUntil ?? ""}`;
  const answeredAt = new Map<string, number>();
  const announced = new Set<string>();
  return {
    begin() { return ++seq; },
    /** Start sending an answer; false while another answer is being sent (a double tap). */
    answer(q: JobQuestion, now: number) {
      if (sending) return false;
      sending = id(q); answeredAt.set(sending, now); floor = ++seq;
      return true;
    },
    settle(q: JobQuestion) { if (sending === id(q)) sending = ""; },
    failed(q: JobQuestion) { if (sending === id(q)) sending = ""; answeredAt.delete(id(q)); },
    accept(token: number, list: JobQuestion[], now: number) {
      // Out of date: started before an answer or before a refresh already shown (refreshes can finish out of order).
      // The floor only ever rises, so an older reply can never roll the card back or clear an answered instance early.
      if (token <= floor) return null;
      floor = token;
      const waiting = list.filter(q => q.waitingUntil !== null && q.waitingUntil > now);
      const ids = new Set(waiting.map(id));
      for (const k of [...answeredAt.keys()]) if (!ids.has(k)) answeredAt.delete(k);
      for (const k of [...announced]) if (!ids.has(k)) announced.delete(k);
      const visible = waiting.filter(q => { const at = answeredAt.get(id(q)); return at === undefined || now - at > hold; });
      const announce = visible.filter(q => !announced.has(id(q)));
      for (const q of announce) announced.add(id(q));
      return { visible, announce };
    },
  };
}

const ACTIVE_PLAN = new Set(["proposed", "approved", "running", "expired"]);  // expired cards never ran
/** True when a job application (from any entry point: the panel, June's chat, another tab, a reload) has newly
 * finished, so the jobs list should be fetched again. `seen` remembers outcomes already handled; `initial` records
 * the ones already finished when the panel opened, without asking for a refresh (its first load covers them). */
export function finishedApplications(seen: Set<string>, plans: { id: string; status: string; steps: { capability: string }[] }[], initial = false) {
  let changed = false;
  for (const plan of plans) {
    if (ACTIVE_PLAN.has(plan.status) || !plan.steps.some(step => step.capability === "jobs.apply")) continue;
    const mark = `${plan.id}:${plan.status}`;
    if (seen.has(mark)) continue;
    seen.add(mark);
    if (!initial) changed = true;
  }
  return changed;
}

/** Orders replies for one list: only the most recently started request may update it. */
export function newestReplies() {
  let latest = 0;
  return { begin() { return ++latest; }, take(token: number) { return token === latest; } };
}
