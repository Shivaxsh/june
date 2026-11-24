"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import type { ChatEvent, ChatMessage, ModelStatus } from "@/lib/chat-types";
import { MAX_MESSAGE_LENGTH } from "@/lib/chat-types";
import { JUNE_VERSION } from "@/lib/version";
import { readJsonLines } from "@/lib/ndjson";
import { prepareContext, type ContextMessage } from "@/lib/context";
import { CONTINUE_PROMPT, isContinueIntent, joinTurns, speechLead, spokenNotice, unclosedFence } from "@/lib/continuation";

import HudOrb, { type ClusterInfo } from "./orb/HudOrb";
import Constellation, { useConstellation } from "./hud/Constellation";
import Sky from "./hud/Sky";
import ConstellationClassic from "./hud/ConstellationClassic";
import Atlas from "./hud/Atlas";
import SpecimenRail from "./hud/SpecimenRail";
import Subtitles from "./hud/Subtitles";
import { DESIGN } from "@/lib/hud/design";
import Counter from "./hud/Counter";
import Elapsed from "./hud/Elapsed";
import { isWaitStage, waitLabel } from "@/lib/wait-status";
import { CLUSTER_RGB, rgb } from "@/lib/hud/palette";
import { displayAddress } from "@/lib/hud/address";
import AudioPanel from "./orb/AudioPanel";
import OrbControls from "./orb/OrbControls";
import { useAudio } from "./orb/useAudio";
import { resolveOrb, type Preview } from "@/lib/orb/state";

import { useVoice } from "./voice/useVoice";
import VoicePanel from "./voice/VoicePanel";
import ReplyStatus from "./voice/ReplyStatus";
import { useHandsFree } from "./voice/useHandsFree";
import HandsFreePanel, { handsFreeLabels } from "./voice/HandsFreePanel";
import { mergeTranscript, spokenChatReply, spokenText } from "@/lib/voice/sentences";

import ModelPicker from "./ModelPicker";
import CitationSources from "./knowledge/CitationSources";
import DocumentsPanel from "./knowledge/DocumentsPanel";
import {useDocuments} from "./knowledge/useDocuments";
import {libraryScope,parseStored,validateCitations,validatedDocumentReply,type Citation} from "@/lib/knowledge-types";
import LibraryPanel from "./memory/LibraryPanel";
import ActionCard from "./actions/ActionCard";
import HandsPanel from "./actions/HandsPanel";
import IntegrationsPanel from "./integrations/IntegrationsPanel";
import PlanCard from "./integrations/PlanCard";
import { parsePlan } from "@/lib/integrations";
import DailyPanel from "./daily/DailyPanel";
import { useDaily } from "./daily/useDaily";
import { useIntegrations } from "./integrations/useIntegrations";
import CommandsPanel from "./integrations/CommandsPanel";
import MailJobsPanel from "./integrations/MailJobsPanel";
import ScreenPanel from "./integrations/ScreenPanel";
import JobQuestionCard from "./integrations/JobQuestionCard";
import TransactionCard from "./transactions/TransactionCard";
import TransactionsPanel from "./transactions/TransactionsPanel";
import { useTransactions } from "./transactions/useTransactions";
import { parseTransaction } from "@/lib/transactions";
import { approvalFailureSpeech, arm as armVoiceReview, CLARIFY, isDefiniteRejection, outcomeSpeech, reviewKind, voiceApprove, VoiceConsent, waitForOutcome } from "@/lib/commerce-voice";
import { getTransaction, respond as respondToBooking } from "@/lib/transactions";
import CreationsPanel from "./knowledge/CreationsPanel";
import { useActions } from "./actions/useActions";
import { parseAction } from "@/lib/actions";
import TimerCard from "./timers/TimerCard";
import TimerChip from "./timers/TimerChip";
import TimersPanel from "./timers/TimersPanel";
import { useTimers } from "./timers/useTimers";
import { claimTimer, parseTimer, timerPhrase } from "@/lib/timers";
import ReminderCard from "./reminders/ReminderCard";
import RemindersPanel from "./reminders/RemindersPanel";
import { useReminders } from "./reminders/useReminders";
import { alertableReminders, claimReminder, isConflict, parseReminder, parseSeries, reminderKey, reminderPhrase } from "@/lib/reminders";
import SeriesCard from "./reminders/SeriesCard";
import { getToday, todayKey, todayPhrase } from "@/lib/daily";
import { alertReady, enqueueAlert, openGate, shouldAnnounce, takeAlert, updateGate, type AlertGate, type TimerAlert } from "@/lib/timer-alerts";
import { useLibrary } from "./memory/useLibrary";
import { libraryRequest, LibraryError, type SavedConversation } from "@/lib/memory-types";

// Stable empties keep the constellation layout from recomputing while the library loads.
const NO_MEMORIES: { id: string; source: string | null }[] = [];
const NO_CHATS: { id: string; title: string }[] = [];
// A reply continued past the length limit is one bubble made of saved segments (`parts`).
// `latestId` is the newest saved segment, the one a further continuation starts from;
// `resume` holds the saved chain while a continuation is in flight, so a stop restores it.
type Chain = { parts: string[]; latestId: string; limited: boolean; incomplete: boolean };
type DisplayMessage = ChatMessage & { id: string; state?: "pending" | "complete" | "stopped" | "failed"; limited?: boolean; incomplete?: boolean; repetitionStopped?: boolean; memoryIds?: string[]; citations?:Citation[]; parts?: string[]; latestId?: string; resume?: Chain; actionId?: string; planId?: string; transactionId?: string; timerId?: string; reminderId?: string; reminderSeriesId?: string };
const restored = (message: DisplayMessage): DisplayMessage => message.resume
  ? { ...message, content: message.resume.parts.join(""), parts: message.resume.parts.length > 1 ? message.resume.parts : undefined, latestId: message.resume.latestId, limited: message.resume.limited, incomplete: message.resume.incomplete, state: "complete", resume: undefined }
  : message;

export default function Chat() {
  const audio = useAudio();
  const manualTakeover = useRef<() => void>(() => {});
  const voice = useVoice(audio.stop, () => manualTakeover.current());
  const [preview, setPreview] = useState<Preview>("auto");
  const [still, setStill] = useState(false);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const messagesRef = useRef(messages); messagesRef.current = messages;
  // The saved segment the server would continue now. It can sit behind a later
  // application notice ("is it finished?"), so it is tracked rather than read off the last bubble.
  const [resumable, setResumable] = useState<string | null>(null);
  const resumableRef = useRef(resumable); resumableRef.current = resumable;
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [modelChanging, setModelChanging] = useState(false);
  const modelChangingRef = useRef(false);
  const [error, setError] = useState("");
  const [timing, setTiming] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [contextLimited, setContextLimited] = useState(false);
  const history = useRef<ContextMessage[]>([]);
  const active = useRef<AbortController | null>(null);
  const requestId = useRef(0);
  const busyRef = useRef(false);
  const composer = useRef<HTMLTextAreaElement>(null);
  const conversation = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const spokenTurn = useRef<{ turn: number; request: number; complete: boolean } | null>(null);

  const [conversationId, setConversationId] = useState<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const conversationOpenGeneration = useRef(0);
  const [systemsOpen, setSystemsOpen] = useState(false);
  const [chipFocus, setChipFocus] = useState(-1);
  const [lastReply, setLastReply] = useState<{ retrieval?: number; answer?: number; total?: number } | null>(null);
  const [lastCited, setLastCited] = useState<{ documents: string[]; chat: string | null }>({ documents: [], chat: null });
  const [shockSeq, setShockSeq] = useState(0);
  const specimen = DESIGN === "specimen", observatory = DESIGN === "observatory";
  // Specimen: the conversation lives in a slide-in history drawer; the atlas and rail need the hero and rail boxes.
  const [historyOpen, setHistoryOpen] = useState(false);
  const historyToggle = useRef<HTMLButtonElement>(null);
  const hero = useRef<HTMLElement>(null), rail = useRef<HTMLElement>(null);
  const orbLayer = useRef<HTMLDivElement>(null);
  // A citation comet reached the orb: the matching source button in the reply lights up once.
  const cometArrived = useCallback((documentId: string) => {
    if (typeof document === "undefined") return;
    for (const button of document.querySelectorAll<HTMLElement>(`.citation-sources button[data-document-id="${CSS.escape(documentId)}"]`)) {
      button.classList.remove("is-arrived"); void button.offsetWidth; button.classList.add("is-arrived");
      window.setTimeout(() => button.classList.remove("is-arrived"), 1400);
    }
  }, []);
  const systemsButton = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLElement>(null);
  const [libraryTab, setLibraryTab] = useState<{ tab: "memory" | "chats" | "personality"; seq: number }>();
  const drawerReturn = useRef<HTMLElement | null>(null);
  const [deletedSources,setDeletedSources]=useState<string[]>([]);
  // Real waiting signals only: the stage the server reported, when the request started, and whether text has arrived.
  const [waitStage,setWaitStage]=useState("");
  const [waitSince,setWaitSince]=useState(0);
  const [writing,setWriting]=useState(false);
  // Hands: server-proposed Mac actions. Chat only displays them; the card alone can approve.
  const actions = useActions();
  const integrations = useIntegrations();
  const transactions = useTransactions(integrations.plans);
  // Spoken approval of one simulated purchase: armed only by the server after June's native playback of that exact review.
  const consent = useRef(new VoiceConsent());
  const daily = useDaily();
  // Timers: the server owns time and completion; a finished timer is claimed once and spoken when June is idle.
  const timers = useTimers();
  const claimed = useRef(new Set<string>());
  const [timerAlerts, setTimerAlerts] = useState<TimerAlert[]>([]);
  // Today's Calendar events, shown when the page opens and spoken once per day and per set of events.
  const [todayNotice, setTodayNotice] = useState<{ phrase: string; key: string } | null>(null);
  const todaySpoken = useRef(false);
  const reminders = useReminders();
  const alertItemsRef = useRef<{ id: string; status: string }[]>([]);
  const alertGate = useRef<AlertGate>(null);
  // Timers this page has seen running, recorded whether or not June is busy.
  const seenActive = useRef(new Set<string>());
  const [gateTick, setGateTick] = useState(0);
  const documents=useDocuments(ids=>{
    setDeletedSources(previous=>[...new Set([...previous,...ids])]);
    // Replayed historical document audio is also invalidated on deletion.
    if(busyRef.current || messages.some(m=>m.citations?.some(c=>ids.includes(c.documentId)))){
      interrupt('source-deleted');handsFree.stop();voice.cancel();audio.stop();history.current=[];
      setAnnouncement("Source deleted. June stopped affected replies and refreshed the available sources.");
    }
  });
  const extraction = useRef<AbortController | null>(null);
  const [suggestAfter, setSuggestAfter] = useState<{conversationId:string;turnId:string}|null>(null);
  const library = useLibrary(() => {
    interrupt('library-changed'); handsFree.stop(); voice.cancel(); audio.stop(); history.current=[];
    // The server ties a continuation to the saved-store revision; a change makes the old chain stale.
    setResumable(null);
    setContextLimited(false);
    const cid=conversationIdRef.current;
    if(cid) void libraryRequest(`conversations/${cid}`).catch(e=>{
      if(e instanceof LibraryError && e.status===404 && conversationIdRef.current===cid){
        conversationIdRef.current=null;setConversationId(null);setMessages([]);
        setAnnouncement("This conversation was deleted or expired. Your next message starts a new chat.");
      }
    });
    setAnnouncement("Saved information changed. Model context reset; visible chat history is kept separately.");
  });
  function cancelExtraction() {
    extraction.current?.abort();extraction.current=null;setSuggestAfter(null);
    void libraryRequest("cancel","POST",{}).catch(()=>{});
  }

  // A wake phrase or natural interruption invalidates the old request. Late network,
  // transcription and synthesis callbacks cannot resume an interrupted turn.
  function interrupt(reason = 'unspecified') {
    if (reason === 'wake') setShockSeq(n => n + 1);  // the sky's interruption shockwave
    conversationOpenGeneration.current++;
    cancelExtraction();
    spokenTurn.current = null;
    requestId.current++;
    active.current?.abort(); active.current = null;
    busyRef.current = false; setBusy(false); setWaitStage("");
    voice.stopVoice("voice-turn-cancelled");
    // An interrupted continuation returns to its last saved segment, the point June continues from.
    setMessages(previous => previous.map(message => message.state !== "pending" ? message : message.resume ? restored(message) : { ...message, state: "stopped" }));
  }
  /** Speak `text` as June's reply to hands-free `turn`, in that turn's own native context (never an out-of-band
   * announcement: native capture is active, and the alert queue stays the only place that announces). */
  function speakTurn(turn: number, text: string) {
    const id = ++requestId.current;
    spokenTurn.current = { turn, request: id, complete: true };
    voice.begin(id, true, { voiceSessionId: handsFree.sessionId(), turnId: turn });
    voice.push(id, text); voice.finish(id);
    setAnnouncement(text);
    return voice.requestId();
  }
  const handsFree = useHandsFree({
    wake: () => { interrupt('wake'); setPreview("auto"); },
    transcript: (content, turn) => {
      // A reply to an armed spoken review: an explicit go-ahead is forwarded (the server checks what it heard, when and
      // for which quote); a bare yes asks again; anything else (a correction, question…) goes to chat and voids the review.
      const decision = consent.current.route(content, handsFree.sessionId(), Date.now());
      if (decision.kind === "pass") { void send({ content, voiceTurn: turn }); return; }
      if (decision.kind === "reread") {
        // An ambiguous "yes": re-read the exact review in this turn and re-arm a fresh token once it has played in full.
        const requestId = speakTurn(turn, `${CLARIFY} ${decision.review.text}`);
        consent.current.expect(decision.review, handsFree.sessionId(), requestId);
        return;
      }
      const armed = decision.armed;
      handsFree.activity("generating");
      void voiceApprove(armed, turn)
        .then(async ({ plan, serverNow }) => {
          integrations.upsert(plan, serverNow);
          // Speak the verified simulated receipt (or an honest unknown), never just "completing…".
          const outcome = await waitForOutcome(armed.transactionId, id => getTransaction(id), { kind: armed.kind });
          if (outcome) transactions.upsert(outcome);
          speakTurn(turn, outcomeSpeech(outcome, armed.kind));
        })
        .catch(async failure => {
          // The response may be lost after the server committed: reconcile read-only, never approve or commit again.
          const outcome = await waitForOutcome(armed.transactionId, id => getTransaction(id), isDefiniteRejection(failure) ? { kind: armed.kind, timeoutMs: 0 } : { kind: armed.kind });
          if (outcome) transactions.upsert(outcome);
          speakTurn(turn, approvalFailureSpeech(failure, outcome, armed.kind));
        });
    },
    cancel: () => interrupt('hands-free-cancel'),
    pause: voice.pauseForInput,
    resume: voice.resumeAfterInput,
    audio: () => ({ audioSource: voice.engine, ownerId: voice.ownerId, voiceId: voice.choices.selected }),
    status: voice.audioStatus, refresh: voice.refreshAudio,
  });
  manualTakeover.current = () => { cancelExtraction(); handsFree.stop(); };
  useEffect(() => {
    const turn = spokenTurn.current;
    if (!handsFree.active || !turn || turn.turn !== handsFree.state.turn || turn.request !== requestId.current) return;
    if (voice.speech.error) { handsFree.stop(voice.speech.error); return; }
    if (voice.speech.phase === "speaking") handsFree.activity("speaking", voice.speech.caption);
    else if (busy) handsFree.activity("generating");
    else if (turn.complete && voice.speech.phase === "idle") handsFree.activity("complete");
  }, [handsFree.active, handsFree.state.turn, busy, voice.speech.phase, voice.speech.error, voice.speech.caption]);

  // June finished speaking a reply in full: if it was the expected review, ask the server to arm voice approval.
  useEffect(() => {
    const finished = voice.speech.completedRequest;
    const due = finished ? consent.current.completed(finished) : null;
    if (!due) return;
    void armVoiceReview(due).then(({ reviewToken, expiresAt }) => consent.current.setArmed(due, reviewToken, expiresAt))
      .catch(() => setAnnouncement("Voice approval isn’t available for this quote right now. Tap Approve on the card to book it."));
  }, [voice.speech.completedRequest]);
  useEffect(() => { if (!handsFree.active) consent.current.disarm(); }, [handsFree.active]);

  const speechBusy = voice.speech.phase !== "idle";
  const recordingBusy = voice.recognition.phase !== "idle" || ["requesting","preparing","listening","transcribing","connecting"].includes(handsFree.state.phase);
  // Alerts wait their turn: never over a reply, June's speech, a recording, or an open conversation turn.
  const alertIdle = !busy && voice.speech.phase === "idle" && voice.recognition.phase === "idle" && ["off", "waiting"].includes(handsFree.state.phase);
  // …and a voice that can actually speak: on first load the provider may still be preparing.
  const alertsReady = alertReady({ idle: alertIdle, speakReplies: voice.speakReplies, voiceSelected: voice.alertOutputWarm ? voice.choices.selected : "" });
  // Timers and reminders share one alert queue under namespaced ids ("timer:…", "reminder:<id>:<revision>":
  // an edited or snoozed reminder is a new occurrence, and an alert for an older revision drops).
  // Occurrences of a paused, stopped or unknown series never speak and are never claimed.
  const speakable = alertableReminders(reminders.state?.reminders ?? [], reminders.state?.series ?? []);
  const alertItems = [
    ...(timers.state?.timers ?? []).map(t => ({ id: `timer:${t.id}`, status: t.status })),
    ...speakable.map(r => ({ id: reminderKey(r), status: r.status })),
    ...(todayNotice ? [{ id: `today:${todayNotice.key}`, status: "completed" }] : []),
  ];
  alertItemsRef.current = alertItems;
  useEffect(() => {
    for (const t of timers.state?.timers ?? []) if (t.status === "active") seenActive.current.add(`timer:${t.id}`);
    for (const r of speakable) if (r.status === "active") seenActive.current.add(reminderKey(r));
  }, [timers.state, reminders.state]);
  // A finished timer or due reminder is claimed at most once per tab, and only when June could speak it now:
  // muted or busy leaves it visual (its card), so the server's single announcement is not spent on a tab that cannot speak.
  useEffect(() => {
    if (!alertsReady) return;
    for (const t of timers.state?.timers ?? []) {
      if (t.status !== "completed" || claimed.current.has(`timer:${t.id}`)) continue;
      claimed.current.add(`timer:${t.id}`);
      void claimTimer(t).then(reply => {
        // Monotonic merge: a late claim reply cannot bring back a timer already dismissed or cancelled.
        timers.upsert(reply.timer, reply.serverNow);
        // Seen running here: speaks when June is free, however long the reply took. Already finished when the
        // page opened: speaks only if recent, otherwise its card waits (Hear again).
        if (shouldAnnounce({ announce: reply.announce, timer: reply.timer, serverNow: reply.serverNow, witnessedActive: seenActive.current.has(`timer:${reply.timer.id}`) })) setTimerAlerts(queue => enqueueAlert(queue, { id: `timer:${reply.timer.id}`, phrase: timerPhrase(reply.timer) }, alertItemsRef.current));
      }).catch(() => { claimed.current.delete(`timer:${t.id}`); });
    }
    for (const r of speakable) {
      if (r.status !== "completed" || claimed.current.has(reminderKey(r))) continue;
      const key = reminderKey(r);
      claimed.current.add(key);
      void claimReminder(r).then(reply => {
        reminders.upsert(reply.reminder, reply.serverNow);
        // An old overdue reminder first seen on opening the page stays visual; one seen scheduled here speaks.
        if (shouldAnnounce({ announce: reply.announce, timer: reply.reminder, serverNow: reply.serverNow, witnessedActive: seenActive.current.has(reminderKey(reply.reminder)) })) setTimerAlerts(queue => enqueueAlert(queue, { id: reminderKey(reply.reminder), phrase: reminderPhrase(reply.reminder) }, alertItemsRef.current));
        // 409: another tab edited or snoozed it first. Keep this old revision's key claimed and fetch the new one.
      }).catch(failure => { if (isConflict(failure)) void reminders.refresh(); else claimed.current.delete(key); });
    }
  }, [timers.state, reminders.state, alertsReady]);
  useEffect(() => {
    let alive = true;
    void getToday().then(({ today }) => {
      const phrase = todayPhrase(today);
      if (!alive || !phrase) return;
      const key = todayKey(today);
      let seen = "";
      try { seen = localStorage.getItem("june-today-notice-v1") ?? ""; } catch {}
      if (seen !== key) setTodayNotice({ phrase, key });
    }).catch(() => {});
    return () => { alive = false; };
  }, []);
  const settleToday = (key: string) => { try { localStorage.setItem("june-today-notice-v1", key); } catch {} };
  useEffect(() => {
    // Spoken only when June is free with a ready, unmuted voice; otherwise the notice stays on screen.
    // It joins the one alert queue, so it never talks over a timer or reminder; dismissing it first drops it.
    if (!(todayNotice && alertsReady) || todaySpoken.current) return;
    todaySpoken.current = true; settleToday(todayNotice.key);
    setTimerAlerts(queue => enqueueAlert(queue, { id: `today:${todayNotice.key}`, phrase: todayNotice.phrase }, alertItemsRef.current));
  }, [todayNotice, alertsReady]);
  // One alert at a time: each waits until the previous one has been heard (or never started), and is
  // dropped if its timer or reminder was dismissed or cancelled meanwhile.
  useEffect(() => {
    if (!voice.speakReplies) { if (timerAlerts.length) setTimerAlerts([]); return; }
    const gate = updateGate(alertGate.current, voice.speech.phase, Date.now()); alertGate.current = gate;
    const { play, queue } = takeAlert(timerAlerts, alertItems, { idle: alertsReady, gate });
    if (queue.length !== timerAlerts.length) setTimerAlerts(queue);
    if (play) { alertGate.current = openGate(Date.now()); setAnnouncement(play.phrase); voice.announce(play.phrase); }
    if (alertGate.current && !alertGate.current.heard) { const tick = setTimeout(() => setGateTick(n => n + 1), 1000); return () => clearTimeout(tick); }
  }, [timerAlerts, alertsReady, voice.speech.phase, timers.state, reminders.state, gateTick, voice.speakReplies]);
  useEffect(() => {
    if (recordingBusy || handsFree.active) { cancelExtraction(); return; }
    // Do not compete with a person's immediate follow-up or replace the
    // model's reusable chat prefix while the conversation window is open.
    if (!suggestAfter || busy || speechBusy || library.temporary || handsFree.state.phase === "followup") return;
    const controller=new AbortController(); extraction.current=controller;
    const timer=setTimeout(() => {
      void libraryRequest("extract","POST",suggestAfter,controller.signal).then(() => {if(!controller.signal.aborted) void library.refresh();}).catch(()=>{}).finally(()=>{if(!controller.signal.aborted)setSuggestAfter(null);});
    },700);
    return () => { clearTimeout(timer);controller.abort(); };
  },[suggestAfter,busy,speechBusy,recordingBusy,library.temporary,handsFree.state.phase,handsFree.active]);
  useEffect(() => {
    // Leaving the page cancels everything. A hidden tab releases the microphone,
    // sound and voice, but a reply already being written is allowed to finish
    // and be saved: the embedded browser can report "hidden" for a few
    // milliseconds during layout, which must not throw away a minute of work.
    // useVoice, useAudio and useHandsFree each release their own media on a sustained hide.
    const stop = () => { interrupt('page-left'); voice.cancel(); audio.stop(); handsFree.stop(); };
    const visibility = () => console.debug('[June visibility]', JSON.stringify({ at: Date.now(), hidden: document.hidden, focused: document.hasFocus() }));
    window.addEventListener("pagehide",stop); document.addEventListener("visibilitychange", visibility);
    return () => {extraction.current?.abort();window.removeEventListener("pagehide",stop);document.removeEventListener("visibilitychange", visibility);};
  },[]);
  useEffect(() => {voice.setExpression(library.temporary ? "steady" : library.data?.profile.expression || "steady");},[library.data?.profile.expression,library.temporary]);

  function openConversation(chat:SavedConversation,token:number) {
    if(token!==conversationOpenGeneration.current)return;
    newChat();setConversationId(chat.id);conversationIdRef.current=chat.id;
    // A reopened action shows its current server status, never a stale copy.
    void actions.refresh();
    // Continuation segments join into the bubble they continue; the latest segment decides the warning.
    const joined = joinTurns(chat.turns), last = joined[joined.length - 1];
    setResumable(chat.resumable !== undefined ? chat.resumable : last && last.status === "complete" && (last.limited || last.incomplete) && !parseStored(last.citations, []).length ? last.latestId : null);
    setMessages(joined.flatMap(t => { const content=t.parts.join(""); return [{role:"user" as const,content:t.user,id:`user-${t.id}`},{role:"assistant" as const,content,parts:t.parts.length>1?t.parts:undefined,latestId:t.latestId,actionId: typeof t.actionId === "string" ? t.actionId : undefined,timerId: typeof t.timerId === "string" ? t.timerId : undefined,reminderId: typeof t.reminderId === "string" ? t.reminderId : undefined,reminderSeriesId: typeof t.reminderSeriesId === "string" ? t.reminderSeriesId : undefined,limited:t.limited,incomplete:t.status==="complete"&&(t.incomplete||unclosedFence(content)),id:`assistant-${t.id}`,state:t.status === "pending" ? "stopped" as const : t.status,memoryIds:parseStored(t.memories,[]),citations:(()=>{try{return validateCitations(parseStored(t.citations,[]));}catch{return [];}})()}]; }));
    // Inference context is loaded and filtered by the Python server, never reconstructed from displayed history.
    setAnnouncement("Saved conversation reopened.");
  }

  async function reconnect() {
    try {
      const response = await fetch("/api/status", { cache: "no-store" });
      const data: unknown = await response.json();
      if (!response.ok || !data || typeof data !== "object"
        || !("state" in data) || !("model" in data) || !("message" in data)
        || !["ready", "offline", "missing", "error"].includes(String(data.state))
        || typeof data.model !== "string" || typeof data.message !== "string") throw new Error();
      setStatus(data as ModelStatus);
    } catch {
      setStatus({ state: "offline", model: "Local model", message: "June’s server is unavailable. Restart June, then reconnect." });
    }
  }

  useEffect(() => {
    void reconnect();
    const timer = setInterval(() => { if (!busyRef.current) void reconnect(); }, 20000);
    return () => { clearInterval(timer); active.current?.abort(); };
  }, []);

  useEffect(() => {
    const panel = conversation.current;
    if (panel && nearBottom.current) panel.scrollTop = panel.scrollHeight;
  }, [messages]);

  function newChat() {
    conversationOpenGeneration.current++;
    cancelExtraction(); setConversationId(null);conversationIdRef.current=null;setResumable(null);
    handsFree.stop(); spokenTurn.current = null;
    audio.stop(); voice.cancel(true); setPreview("auto");
    requestId.current += 1;
    active.current?.abort();
    active.current = null;
    history.current = [];
    setContextLimited(false);
    busyRef.current = false;
    setBusy(false);
    setMessages([]);
    setDraft("");
    setError("");
    setTiming(""); setWaitStage(""); setLastCited({ documents: [], chat: null });
    setAnnouncement("New chat. Earlier saved conversations remain in Recent chats.");
    nearBottom.current = true;
    composer.current?.focus();
  }

  async function send(input?: { content: string; voiceTurn?: number }) {
    const automatic = input?.voiceTurn !== undefined;
    const voiceSessionId = automatic ? handsFree.sessionId() : '';
    if (automatic && !voiceSessionId) return;
    if (!automatic) handsFree.stop();
    const content = (input?.content ?? draft).trim();
    if (!content || modelChangingRef.current || busyRef.current || voice.recognition.phase !== "idle" || content.length > MAX_MESSAGE_LENGTH) return;
    if ((!library.data || library.error) && !library.temporary) {setError("Private storage is unavailable. Retry storage or explicitly choose temporary chat.");return;}
    // "continue" (typed, spoken or the Continue button) on the latest saved partial reply resumes
    // that chain on the server. Temporary chats have no saved segments: "continue" stays a normal message.
    const target = resumableRef.current ? messagesRef.current.find(m => m.role === "assistant" && m.latestId === resumableRef.current) : undefined;
    const continuing: Chain | null = !library.temporary && conversationIdRef.current && isContinueIntent(content)
      && target?.state === "complete" && !target.repetitionStopped && target.latestId
      ? { parts: target.parts ?? [target.content], latestId: target.latestId, limited: !!target.limited, incomplete: !!target.incomplete } : null;
    const base = continuing ? continuing.parts.join("") : "";
    cancelExtraction();
    setWaitStage(""); setWriting(false); setWaitSince(Date.now());
    setPreview("auto");
    busyRef.current = true;
    setBusy(true);
    setError("");
    setTiming("");
    if (!input) setDraft("");
    const id = ++requestId.current;
    spokenTurn.current = input?.voiceTurn !== undefined ? { turn: input.voiceTurn, request: id, complete: false } : null;
    voice.begin(id, automatic, automatic ? { voiceSessionId, turnId: input!.voiceTurn! } : undefined);
    const speakingRequest = voice.requestId();  // the native request that will speak this reply
    if (automatic) consent.current.disarm();  // a new spoken turn: any earlier review is void
    const controller = new AbortController();
    active.current = controller;
    const user: ChatMessage = { role: "user", content };
    const assistantId = continuing ? target!.id : `assistant-${id}`;
    const prepared = prepareContext(history.current, user);
    const context = prepared.messages;
    if (prepared.limited && !continuing) setContextLimited(true);
    const started = performance.now();
    let firstToken = 0;
    let reply = "";
    let complete = false;
    let replyLimited = false;
    let incomplete = false;
    let savedTurnId = "";
    let repetitionStopped = false;
    const stageTimings: Record<string, number> = {};
    let memoryIds: string[] = [];
    let generalReply = false;
    let citations:Citation[]=[];
    let actionId: string | undefined;
    let planId: string | undefined;
    let transactionId: string | undefined;
    let timerId: string | undefined;
    let reminderId: string | undefined;
    let reminderSeriesId: string | undefined;
    const turnId=crypto.randomUUID();
    let savedConversation=conversationIdRef.current;
    nearBottom.current = true;
    setMessages(previous => continuing
      ? previous.map(message => message.id === assistantId ? { ...message, state: "pending", parts: [...continuing.parts, ""], resume: continuing } : message)
      : [...previous, { ...user, id: `user-${id}` }, { role: "assistant", content: "", id: assistantId, state: "pending" }]);
    setAnnouncement("June is preparing a reply.");

    // React state drives the screen; successful message pairs drive model context.
    // Failed or stopped replies stay visible but never become hidden context.
    const update = (state: DisplayMessage["state"]) => {
      if (frame) { cancelAnimationFrame(frame); frame = 0; }
      if (id !== requestId.current) return;
      setMessages(previous => previous.map(message => message.id !== assistantId ? message : continuing
        ? { ...message, content: base + reply, parts: [...continuing.parts, reply], state, limited: replyLimited, incomplete, repetitionStopped, ...(state === "complete" ? { latestId: savedTurnId, resume: undefined } : {}) }
        : { ...message, content: reply, state, limited: replyLimited, incomplete, repetitionStopped, memoryIds, citations, latestId: savedTurnId || undefined, actionId, planId, transactionId, timerId, reminderId, reminderSeriesId }));
    };
    const restoreChain = () => setMessages(previous => previous.map(message => message.id === assistantId ? restored(message) : message));
    // Streamed words appear as they arrive, at most once per frame.
    let frame = 0;
    const showProgress = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => { frame = 0; update("pending"); });
    };
    // General replies stream across multiple deltas. Document replies arrive in
    // one delta and must wait for done/citation validation before any speech.
    let deltaCount = 0;
    let spoken = "";
    // A continuation inside an open code fence is wrapped in a matching fence for speech only,
    // so continued code is never read aloud and earlier prose is never sent again.
    const lead = continuing ? speechLead(base) : "";
    const speakProgress = () => {
      // Raw JSON is never spoken. Fenced code (closed or still open) is stripped by the speech
      // cleaner, so a reply that starts with code still speaks the prose after its closing fence.
      // A reply that opens with a json fence may be a transport envelope: it waits for done validation.
      if ((!complete && deltaCount < 2) || repetitionStopped || (!lead && /^\s*[\[{]/.test(reply))
        || (!complete && !lead && /^\s*```\s*json\b/i.test(reply))) return;
      const target = spokenChatReply(lead + reply);
      if (!target.startsWith(spoken)) return;
      voice.push(id, target.slice(spoken.length)); spoken = target;
    };
    try {
      if (!library.temporary && !savedConversation) {
        const created=await libraryRequest<{id:string}>("conversations","POST",{},controller.signal);
        controller.signal.throwIfAborted();
        if(id!==requestId.current)return;
        savedConversation=created.id;conversationIdRef.current=created.id;setConversationId(created.id);
      }
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "local", messages: continuing ? [{ role: "user", content: CONTINUE_PROMPT }] : context, knowledge: libraryScope, ...(library.temporary ? {temporary:true} : {conversationId:savedConversation,turnId,...(continuing ? { continueTurn: continuing.latestId } : {})}) }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(typeof detail?.message === "string" ? detail.message : "June could not start a reply. Try again.");
      }
      if (!response.body) throw new Error("Your browser could not read the response stream.");
      for await (const unknownEvent of readJsonLines(response.body)) {
        if (id !== requestId.current) break;
        if (!unknownEvent || typeof unknownEvent !== "object") throw new Error("June sent an invalid update.");
        const event = unknownEvent as ChatEvent;
        if (event.type === "delta" && typeof event.text === "string") {
          if (!firstToken) {
            firstToken = performance.now();
            setWriting(true);
            console.debug('[June timing]', JSON.stringify({ event: 'first-text', at: Date.now(), ...(automatic ? { voiceSessionId, turnId: input!.voiceTurn! } : {}), durationMs: firstToken - started }));
          }
          if (event.text) deltaCount++;
          reply += event.text;
          showProgress(); speakProgress();
        } else if (event.type === "done" && typeof event.model === "string") {
          citations=validatedDocumentReply(reply,event,libraryScope);
          complete = true;
          replyLimited = event.limited === true;
          // The server's flag, or a fence opened and never closed anywhere in the chain.
          incomplete = event.incomplete === true || unclosedFence(base + reply);
          if (!library.temporary) savedTurnId = typeof event.turnId === "string" ? event.turnId : turnId;
          // The server names what can be continued; an older server leaves it to this reply's own flags.
          setResumable(library.temporary ? null : "resumable" in event ? (typeof event.resumable === "string" ? event.resumable : null)
            : (replyLimited || incomplete) && !event.citations?.length ? savedTurnId : null);
          repetitionStopped = event.repetitionStopped === true;
          if (repetitionStopped) { spokenTurn.current = null; voice.stopVoice('repetition-stopped'); }
          memoryIds = Array.isArray(event.memoryIds) ? event.memoryIds : [];
          // A proposal is shown for review only; nothing runs until its card is clicked.
          const proposal = parseAction(event.actionProposal);
          // A reviewed plan (for example, play the chosen playlist) shows its card under this reply.
          const proposedPlan = parsePlan(event.plan);
          if (proposedPlan) { planId = proposedPlan.id; integrations.upsert(proposedPlan, typeof event.serverNow === "number" ? event.serverNow : proposedPlan.createdAt); }
          // A simulated purchase or booking shows its card (offers, quote, receipt) under this reply; its plan card approves.
          if (event.transaction !== undefined && event.transaction !== null) {
            try {
              const t = parseTransaction(event.transaction); transactionId = t.id; transactions.upsert(t);
              // A hands-free reply that reads out this transaction's own proposed review (an awaiting quote, or cancelling a
              // confirmed order): arm voice approval once it has played in full. Nothing else arms.
              const kind = automatic && speakingRequest && proposedPlan ? reviewKind(t, proposedPlan) : null;
              if (kind && proposedPlan)
                consent.current.expect({ transactionId: t.id, planId: proposedPlan.id, revision: proposedPlan.revision, fingerprint: proposedPlan.fingerprint, text: base + reply, kind }, voiceSessionId, speakingRequest);
            } catch { /* malformed: shown as plain text only */ }
          }
          if (proposal) { actionId = proposal.id; actions.upsert(proposal, typeof event.serverNow === "number" ? event.serverNow : proposal.createdAt); }
          const savedSeries = parseSeries(event.series);
          if (savedSeries) { reminderSeriesId = savedSeries.id; reminders.upsertSeries(savedSeries, typeof event.serverNow === "number" ? event.serverNow : savedSeries.createdAt); }
          const savedReminder = parseReminder(event.reminder);
          if (savedReminder) { reminderId = savedReminder.id; reminders.upsert(savedReminder, typeof event.serverNow === "number" ? event.serverNow : savedReminder.createdAt); }
          const startedTimer = parseTimer(event.timer);
          if (startedTimer) { timerId = startedTimer.id; timers.upsert(startedTimer, typeof event.serverNow === "number" ? event.serverNow : startedTimer.createdAt); }
          generalReply = event.provenance === "general";
          if(!library.temporary && event.persistence!=="saved") throw new Error("This reply was not confirmed saved. Check private storage.");
          break;
        } else if (event.type === 'stage' && isWaitStage(event.stage)) {
          setWaitStage(event.stage);
        } else if (event.type === 'timing') {
          if (typeof event.stage === 'string' && /^[a-z][a-z0-9_-]{0,39}$/i.test(event.stage) && typeof event.durationMs === 'number' && Number.isFinite(event.durationMs) && event.durationMs >= 0) stageTimings[event.stage] = event.durationMs;
        } else if (event.type === "error" && typeof event.message === "string") {
          throw new Error(event.message);
        } else throw new Error("June sent an invalid update.");
      }
      controller.signal.throwIfAborted();
      if (id !== requestId.current) return;
      if (!complete || !reply.trim()) throw new Error("The reply ended unexpectedly. Please try again.");
      if (spokenTurn.current?.request === id) spokenTurn.current.complete = true;
      speakProgress();
      // One fixed line explains a cut-off or code-only reply; code itself is never read out.
      const notice = repetitionStopped ? "" : spokenNotice({ limited: replyLimited, incomplete, spokeSomething: !!spokenText(spoken).trim(), hasCode: !!lead || /```|~~~/.test(reply) });
      if (notice) voice.push(id, `\n\n${notice}`);
      if (!repetitionStopped) voice.finish(id, !replyLimited);
      if (!repetitionStopped) {
        // A partial reply keeps its tail in later context; a continuation replaces the chain's entry.
        const partial = replyLimited || incomplete;
        if (!continuing) history.current = [...context, { role: "assistant", content: reply, partial }];
        else {
          // The chain may sit behind a later notice turn: replace its own entry, nothing else.
          const at = history.current.findLastIndex(m => m.role === "assistant" && m.content === base);
          if (at >= 0) history.current = history.current.map((m, i) => i === at ? { role: "assistant", content: base + reply, partial } : m);
        }
      }
      update("complete");
      void library.refresh();
      if(generalReply && !repetitionStopped && !library.temporary && savedConversation) setSuggestAfter({conversationId:savedConversation,turnId});
      const elapsed = ((performance.now() - started) / 1000).toFixed(1);
      const first = ((firstToken - started) / 1000).toFixed(1);
      setTiming(`${elapsed}s total · first text in ${first}s${Object.entries(stageTimings).map(([stage, ms]) => ` · ${stage} ${(ms / 1000).toFixed(1)}s`).join('')}`);
      setLastReply({ retrieval: stageTimings.retrieval, answer: stageTimings.answer, total: performance.now() - started });
      setLastCited({ documents: [...new Set(citations.map(c => c.documentId))], chat: savedConversation });
      if (repetitionStopped && automatic) handsFree.stop("June stopped a repeated reply. Retry manually when you’re ready.");
      setAnnouncement(repetitionStopped ? "Repeated reply stopped. The text is preserved; retry manually." : replyLimited || incomplete ? (library.temporary ? "This reply may be unfinished. Type continue to ask for more." : "This reply may be unfinished. Choose Continue or say continue for the rest.") : "June’s reply is complete.");
    } catch (failure) {
      if (id !== requestId.current) return;
      voice.stopVoice();
      // A stopped reply keeps the words already shown; a failed one may be unvalidated.
      if (!controller.signal.aborted) reply="";
      citations=[];
      if (continuing) { restoreChain();
        if (controller.signal.aborted) setAnnouncement("Continuation stopped. The reply is unchanged; you can continue again.");
        else { setError(failure instanceof Error ? failure.message : "June could not continue this reply."); if (!input) setDraft(content); setAnnouncement("Continuation failed. The reply is unchanged."); void reconnect(); }
      } else if (controller.signal.aborted) {
        update("stopped");
        setAnnouncement("Reply stopped. You can send another message.");
      } else {
        update("failed");
        setError(failure instanceof Error ? failure.message : "June could not finish this reply.");
        if (!input) setDraft(content);
        setAnnouncement(automatic ? "Voice reply failed. Your typed draft is unchanged." : "Reply failed. Your message is back in the input so you can retry.");
        void reconnect();
      }
      if (automatic) handsFree.stop(controller.signal.aborted ? "" : "The local reply failed. Check June’s connection, then enable hands-free again.");
    } finally {
      if (id === requestId.current) {
        active.current = null;
        busyRef.current = false;
        setBusy(false);setWaitStage("");
        if (!input) composer.current?.focus();
      }
    }
  }

  const voiceActivity = { listening: voice.recognition.phase === "listening", speaking: voice.speech.phase === "speaking", requesting: voice.recognition.phase === "requesting", finishing: voice.recognition.phase === "finishing" };
  const automatic = handsFree.state.phase;
  const orb = handsFree.active ? {
    mood: handsFree.state.probing ? "listening" as const : voiceActivity.speaking ? "speaking" as const : ["listening", "followup"].includes(automatic) ? "listening" as const : ["generating", "transcribing", "connecting", "preparing", "requesting"].includes(automatic) ? "thinking" as const : "idle" as const,
    label: handsFree.state.probing ? "Checking microphone sound · voice paused" : voiceActivity.speaking ? "June is speaking · speak to interrupt" : handsFreeLabels[automatic],
  } : resolveOrb(busy, false, preview, audio.phase, voiceActivity);
  const stopAll = () => { handsFree.stop(); interrupt('stop-button'); voice.cancel(); audio.stop(); setAnnouncement("Stopped. Microphone off; ready for another message."); };
  function useTranscript(text: string) {
    const merged = mergeTranscript(draft, text);
    if (merged.length > MAX_MESSAGE_LENGTH) { setError("The combined message is too long. Shorten your draft or transcript before adding it."); return; }
    setDraft(merged); voice.clearTranscript(); setError(""); composer.current?.focus();
  }
  const connection = status?.message || "Connecting to your local model…";
  const handsFreeEnabled = voice.engine === 'native' && !!voice.ownerId && !busy && !modelChanging && (!!library.data && !library.error || library.temporary) && status?.state === "ready" && voice.speakReplies && !!voice.choices.selected && voice.support.recognition;
  const startHandsFree = () => { cancelExtraction(); audio.stop(); voice.cancel(); setPreview("auto"); handsFree.start(); };
  const openSystems = (section?: string) => {
    if (!systemsOpen) drawerReturn.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSystemsOpen(true);
    const [target, tab] = (section ?? "").split(":");
    if (target === "library") setLibraryTab(previous => ({ tab: (tab as "memory" | "chats" | "personality") || "memory", seq: (previous?.seq ?? 0) + 1 }));
    // The shortcut opens the section it lands on, instead of scrolling to a closed one.
    if (target) requestAnimationFrame(() => {
      const element = document.getElementById(`systems-${target}`);
      element?.querySelector("details")?.setAttribute("open", "");
      element?.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    });
  };
  const closeSystems = () => {
    setSystemsOpen(false);
    const back = drawerReturn.current; drawerReturn.current = null;
    (back?.isConnected && !back.closest("#systems") ? back : systemsButton.current)?.focus();
  };
  // The drawer is modal: focus moves in when it opens, Tab stays inside, Escape closes it.
  useEffect(() => {
    if (!systemsOpen) return;
    const panel = drawer.current;
    if (panel && !panel.contains(document.activeElement)) requestAnimationFrame(() => panel.focus({ preventScroll: true }));
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") { closeSystems(); return; }
      if (event.key !== "Tab" || !panel) return;
      const items = [...panel.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])')].filter(item => !item.closest("[inert]") && item.getClientRects().length);
      if (!items.length) { event.preventDefault(); panel.focus(); return; }
      const first = items[0], last = items[items.length - 1], at = document.activeElement;
      if (event.shiftKey && (at === first || at === panel)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (at === last || !panel.contains(at))) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", keys);
    return () => document.removeEventListener("keydown", keys);
  }, [systemsOpen]);

  const readyDocuments = documents.documents.filter(d => d.status === "ready");
  const memoryCount = library.temporary ? null : library.data?.memories.length ?? null;
  const chatCount = library.temporary ? null : library.data?.conversations.length ?? null;
  const address = displayAddress(library.data?.profile.fields.address);
  const modelShort = (status?.model || "Local model").split("/").pop()!.replace(/^(.+?):(\d+(?:\.\d+)?b).*/i, "$1 $2").replace(/[-_]/g, " ").toUpperCase();
  const stateWord = { idle: "Standing by", listening: "Listening", thinking: "Thinking", speaking: "Speaking" }[orb.mood];
  const toolLine = busy ? (writing ? "writing the reply…" : waitStage === "searching" ? "consulting your library…" : waitStage === "answering" ? "composing a reply…" : waitStage === "queued" ? "waiting for the model…" : waitStage === "loading" ? "loading the model…" : "thinking it over…")
    : voice.speech.phase === "speaking" ? "speaking"
    : handsFree.active ? ({ waiting: "awaiting “Hey June”", listening: "listening…", transcribing: "transcribing…", followup: "listening for a follow-up…", generating: "composing a reply…", speaking: "speaking", requesting: "requesting the microphone…", connecting: "connecting to local audio…", preparing: "preparing the microphone…", off: address ? `awaiting instruction, ${address}` : "awaiting instruction" } as Record<string, string>)[handsFree.state.phase] ?? "listening…"
    : status?.state && status.state !== "ready" ? "local model offline · reconnect in Systems"
    : address ? `awaiting instruction, ${address}` : "awaiting instruction";
  const caption = voice.speech.phase === "speaking" && voice.speech.caption ? voice.speech.caption : "";
  const captionStart = Math.max(0, Math.min(caption.length, voice.speech.start || 0)), captionEnd = Math.max(captionStart, Math.min(caption.length, voice.speech.end || 0));
  const lastUser = [...messages].reverse().find(message => message.role === "user")?.content;
  const lastReply_ = [...messages].reverse().find(message => message.role === "assistant" && message.state !== "pending");
  const lastJune = lastReply_?.content;
  // History drawer: Escape closes it and returns focus; a reply with cards, sources or a failure opens it once,
  // so approvals and citations are never hidden behind the subtitles.
  useEffect(() => {
    if (!specimen || !historyOpen) return;
    const keys = (event: KeyboardEvent) => { if (event.key === "Escape" && !systemsOpen) { setHistoryOpen(false); historyToggle.current?.focus(); } };
    document.addEventListener("keydown", keys);
    return () => document.removeEventListener("keydown", keys);
  }, [specimen, historyOpen, systemsOpen]);
  const autoOpened = useRef("");
  const needsHistory = lastReply_ && (lastReply_.planId || lastReply_.transactionId || lastReply_.reminderId || lastReply_.timerId || lastReply_.actionId || lastReply_.citations?.length || lastReply_.state === "failed") ? lastReply_.id : "";
  useEffect(() => {
    if (!specimen) return;
    const key = needsHistory || (error ? "error:" + error : "");
    if (key && key !== autoOpened.current) { autoOpened.current = key; setHistoryOpen(true); }
  }, [specimen, needsHistory, error]);
  const constellationState = busy && waitStage === "searching" ? "searching" : !busy && lastCited.documents.length ? "cited" : "idle";
  const graph = useConstellation({ documents: documents.documents, memories: library.data?.memories ?? NO_MEMORIES, conversations: library.data?.conversations ?? NO_CHATS,
    revision: `${library.data?.revision ?? 0}:${documents.documents.length}:${lastCited.chat ?? ""}` });
  const orbLevel = voice.engine === "native" && voice.speech.phase === "speaking" ? voice.activity : handsFree.active ? handsFree.level : voice.recognition.phase === "listening" ? voice.level : audio.level;
  const openSavedChat = (id: string) => { conversationOpenGeneration.current++; const token = conversationOpenGeneration.current; void libraryRequest<SavedConversation>(`conversations/${encodeURIComponent(id)}`).then(chat => openConversation(chat, token)).catch(() => { if (token === conversationOpenGeneration.current) setError("That chat is no longer available."); }); };
  const clusterInfo: ClusterInfo[] = [
    { name: "Memory", value: memoryCount === null ? "Temporary chat · not saved" : `${memoryCount} approved ${memoryCount === 1 ? "fact" : "facts"}`, hint: "Click to open Memory" },
    { name: "Voice", value: voice.choices.selected ? `Heart · ${library.data?.profile.expression || "steady"} · ${voice.speakReplies ? "on" : "muted"}` : "Heart voice not ready", hint: "Click to open Voice" },
    { name: "Personality", value: address ? `Addresses you as “${address}”` : library.data?.profile.fields.address?.trim() ? "Custom form of address" : "Character profile", hint: "Click to open Personality" },
    { name: "Knowledge", value: `${readyDocuments.length} ${readyDocuments.length === 1 ? "document" : "documents"} · ${readyDocuments.reduce((sum, d) => sum + (d.pages || 0), 0)} pages`, hint: "Click to open Documents" },
    { name: "Hands", value: actions.state ? (actions.state.available ? (actions.state.openVSCodeWithoutApproval ? "Open VS Code · approval remembered" : "Open VS Code · your approval required") : "Mac actions unavailable") : "Hands unavailable", hint: "Click to open Hands" },
    { name: "Ears", value: `Parakeet · hands-free ${handsFree.active ? "on" : "off"}`, hint: "Click to open Hands-free" },
  ];
  const clusterSection = ["library:memory", "voice", "library:personality", "documents", "hands", "handsfree"];
  const seconds = (ms?: number) => ms === undefined ? "—" : `${(ms / 1000).toFixed(1)} s`;
  const firstAudio = voice.speech.timings?.firstAudioMs;
  const hour = new Date().getHours();
  const greeting = hour < 5 ? "Good evening" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  // Values that appear verbatim in a cited quote get a bracket mark and their source number.
  function citedText(content: string, citations?: Citation[]) {
    if (!citations?.length) return content;
    const parts: React.ReactNode[] = []; let key = 0;
    const pattern = /[A-Za-z]*\d[\w.]*(?:\s?(?:GB|TB|MB|GHz|MHz|W|Ti|XT|SFF))?/g;
    let cursor = 0;
    for (const match of content.matchAll(pattern)) {
      const value = match[0].trim().replace(/\.+$/, ""); if (value.length < 3) continue;
      const quotedValue = new RegExp(`(?<![\\p{L}\\p{N}_.])${value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\p{L}\\p{N}_]|\\.\\p{N})`, "iu");
      const source = citations.findIndex(c => quotedValue.test(c.quote));
      if (source < 0) continue;
      parts.push(content.slice(cursor, match.index), <span key={key++} className="hud-mark">{value}<span className="hud-num" aria-label={`source ${source + 1}`}>{source + 1}</span></span>);
      cursor = (match.index ?? 0) + match[0].indexOf(value) + value.length;
    }
    return parts.length ? [...parts, content.slice(cursor)] : content;
  }

  const conversationLog = (
<div ref={conversation} className="conversation hud-panel" role="log" aria-label="Conversation with June" aria-live="off" onScroll={() => {
            const panel = conversation.current;
            if (panel) nearBottom.current = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 100;
          }}>
            {!messages.length && <div className="empty-state hud-greeting"><h2>{greeting}{address ? <>, <em>{address}.</em></> : "."}</h2><p>Everything runs on this Mac. No cloud, no meter running, nobody listening in.</p><div className="suggestions">{["Introduce yourself, June.", "What do you remember about me?", "What’s in my documents?"].map(text => <button key={text} onClick={() => { setDraft(text); composer.current?.focus(); }}>{text}<span aria-hidden="true">↗</span></button>)}</div></div>}
            {messages.map(message => <article key={message.id} className={`message ${message.role}`} aria-label={message.role === "user" ? "Your message" : "June’s message"}><span className="message-label">{message.role === "user" ? "YOU" : "JUNE"}</span><div className="message-text">{message.parts ? message.parts.map((part, i) => <Fragment key={i}>{i > 0 && <span className="continued-mark" aria-hidden="true" title="Continued" />}{part}</Fragment>) : message.content ? (message.role === "assistant" ? citedText(message.content, message.citations) : message.content) : null}{message.state === "pending" && !(message.parts ? message.parts[message.parts.length - 1] : message.content) ? <span className="waiting">{waitLabel(waitStage, { continuing: !!message.parts })}<span aria-hidden="true">…</span><Elapsed since={waitSince} /></span> : !message.content && message.state !== "pending" ? (message.state === "stopped" ? "Reply stopped." : "No reply yet.") : null}</div><ReplyStatus state={message.state} hasContent={!!message.content} limited={message.limited} incomplete={message.incomplete} repetitionStopped={message.repetitionStopped} busy={busy} temporary={library.temporary}
              onContinue={!library.temporary && !!conversationId && !!message.latestId && message.latestId === resumable ? () => void send({ content: CONTINUE_PROMPT }) : undefined} onRetry={() => {
              const index = messages.findIndex(item => item.id === message.id);
              const question = messages[index - 1];
              if (question?.role === 'user') void send({ content: question.content });
            }} />{message.role === "assistant" && message.reminderId && (() => { const r = reminders.state?.reminders.find(x => x.id === message.reminderId); return r && reminders.state ? <ReminderCard reminder={r} series={r.seriesId ? reminders.state.series.find(x => x.id === r.seriesId) : undefined} serverNow={reminders.state.serverNow} onChange={reminders.upsert} onHear={phrase => voice.replay(phrase)} onRefresh={() => void reminders.refresh()} compact /> : null; })()}{message.role === "assistant" && message.reminderSeriesId && (() => { const x = reminders.state?.series.find(y => y.id === message.reminderSeriesId); return x && reminders.state ? <SeriesCard series={x} serverNow={reminders.state.serverNow} onChange={(next, now, reminder) => { reminders.upsertSeries(next, now); if (reminder) reminders.upsert(reminder, now); }} onRefresh={() => void reminders.refresh()} compact /> : null; })()}{message.role === "assistant" && message.timerId && (() => { const t = timers.state?.timers.find(x => x.id === message.timerId); return t && timers.state ? <TimerCard timer={t} serverNow={timers.state.serverNow} receivedAt={timers.receivedAt} onChange={timers.upsert} onHear={phrase => voice.replay(phrase)} compact /> : null; })()}{message.role === "assistant" && message.actionId && (() => { const record = actions.state?.actions.find(a => a.id === message.actionId); return record && actions.state ? <ActionCard record={record} serverNow={actions.state.serverNow} receivedAt={actions.receivedAt} onChange={actions.upsert} onAnnounce={setAnnouncement} onRefresh={() => void actions.refresh()} /> : actions.state ? <p className="message-note">This action is no longer available.</p> : null; })()}{message.role === "assistant" && message.transactionId && transactions.items[message.transactionId] && <TransactionCard transaction={transactions.items[message.transactionId]}
            onChoose={offerId => { const t = transactions.items[message.transactionId!]; void respondToBooking({ conversationId: t.conversationId, select: { offerId } })
              .then(r => { if (r.transaction) transactions.upsert(r.transaction); if (r.plan) integrations.upsert(r.plan, r.serverNow); setAnnouncement(r.reply); })
              .catch(failure => setAnnouncement(failure instanceof Error ? failure.message : "June couldn’t choose that option.")); }} />}{message.role === "assistant" && message.planId && (() => { const plan = integrations.plans.find(p => p.id === message.planId); return plan ? <PlanCard plan={plan} capabilities={new Map((integrations.capabilities ?? []).map(c => [c.id, c]))} serverNow={integrations.serverNow} receivedAt={integrations.receivedAt} onChange={integrations.upsert} onRefresh={() => void integrations.refreshPlans()} onAnnounce={setAnnouncement} /> : null; })()}{message.role === "assistant" && !!message.citations?.length && <CitationSources citations={message.citations} deleted={[...deletedSources,...(documents.loaded?message.citations.filter(c=>!documents.documents.some(d=>d.id===c.documentId)).map(c=>c.documentId):[])]}/>}{message.role === "assistant" && !!message.memoryIds?.length && <details className="used-memories"><summary>Approved facts provided ({message.memoryIds.length})</summary>{message.memoryIds.map(mid=><p key={mid}>{library.data?.memories.find(m=>m.id===mid)?.text || "This saved memory has since been removed."}</p>)}</details>}{message.role === "assistant" && message.state === "complete" && !message.repetitionStopped && <button className="quiet-button hear-reply" disabled={busy || !voice.choices.selected || message.citations?.some(c=>c.deleted || deletedSources.includes(c.documentId)||(documents.loaded&&!documents.documents.some(d=>d.id===c.documentId)))} onClick={() => { setPreview("auto"); voice.replay(spokenChatReply(message.content)); }}>Hear reply</button>}</article>)}
          </div>
  );

  return (
    <div className={`chat-page hud${specimen ? " design-specimen" : observatory ? " design-observatory" : ""}`} data-mood={specimen ? orb.mood : undefined}>
      <header className="masthead hud-masthead">
        <a className="wordmark" href="/" aria-label="June home"><span className="brand-dot" />june</a>
        <span className="hud-version">v{JUNE_VERSION} · local</span>
        {specimen && <span className="sp-tag june-state" aria-hidden="true">{stateWord}</span>}
        <div className="header-actions"><button className="quiet-button" onClick={() => newChat()}>New chat</button><button ref={systemsButton} className="quiet-button hud-systems-button" aria-expanded={systemsOpen} aria-controls="systems" onClick={() => systemsOpen ? closeSystems() : openSystems()}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10" /></svg>Systems</button></div>
      </header>

      <main className="chat-shell hud-shell">
        <section ref={hero} className="hud-hero" aria-label="June">
          <div className="hud-orb-layer" ref={orbLayer}>
            <HudOrb mood={orb.mood} focus={chipFocus} still={still} info={clusterInfo} address={address}
              level={orbLevel}
              onCluster={cluster => { if (clusterSection[cluster]) openSystems(clusterSection[cluster]); }} onCore={() => setAnnouncement("June says hello.")} />
          </div>
          {observatory && <Sky graph={graph} conversations={library.data?.conversations ?? NO_CHATS} memoryIds={(library.data?.memories ?? NO_MEMORIES).map(m => m.id)}
            state={constellationState} cited={lastCited.documents} citedKey={lastCited.documents.length ? `${lastCited.chat ?? ""}:${lastCited.documents.join(",")}` : ""}
            activeChat={conversationId} level={orbLevel} listening={orb.mood === "listening"} thinking={orb.mood === "thinking"} shockSeq={shockSeq}
            hitArea={orbLayer} onOpenChat={openSavedChat} onCometArrive={cometArrived} />}
          {specimen && <>
            <Atlas graph={graph} conversations={library.data?.conversations ?? NO_CHATS} memoryIds={(library.data?.memories ?? NO_MEMORIES).map(m => m.id)}
              numbers={{ params: status?.state === "ready" ? status.parameters ?? null : null, chats: chatCount, memories: memoryCount, docs: readyDocuments.length, answerMs: lastReply?.answer ?? lastReply?.total ?? null, firstAudioMs: firstAudio ?? null }}
              state={constellationState} cited={lastCited.documents} citedKey={lastCited.documents.length ? `${lastCited.chat ?? ""}:${lastCited.documents.join(",")}` : ""}
              activeChat={conversationId} level={orbLevel} listening={orb.mood === "listening"} thinking={orb.mood === "thinking"} shockSeq={shockSeq}
              hitArea={hero} orbBox={orbLayer} railBox={rail} onOpenChat={openSavedChat} onCometArrive={cometArrived} />
            <SpecimenRail ref={rail} params={status?.state === "ready" ? status.parameters ?? null : null} level={orbLevel} micLive={handsFree.active}
              rows={[
                { label: "Model", value: status?.state === "ready" ? modelShort : "offline", onOpen: () => openSystems("model") },
                { label: "Voice", value: voice.speakReplies ? "Heart · on" : "Heart · muted", onOpen: () => voice.setSpeakReplies(!voice.speakReplies), pressed: voice.speakReplies },
                { label: "Ears", value: handsFree.active ? "Parakeet · live" : "Parakeet · off", onOpen: () => openSystems("handsfree") },
                { label: "Memory", value: library.temporary ? "temporary" : "saved", onOpen: () => openSystems("library") },
                { label: "Library", value: `${readyDocuments.length} docs · ${memoryCount ?? "–"} mem · ${chatCount ?? "–"} chats`, onOpen: () => openSystems("library:chats") },
              ]}
              timings={[{ label: "Retrieval", value: seconds(lastReply?.retrieval) }, { label: "Answer", value: seconds(lastReply?.answer ?? lastReply?.total) }, { label: "First audio", value: seconds(firstAudio) }]}
              parts={clusterInfo.map((item, i) => ({ name: item.name, onOpen: () => { if (clusterSection[i]) openSystems(clusterSection[i]); } }))} />
          </>}
          <div className="hud-grid">
            {observatory && <Constellation graph={graph} state={constellationState} onOpenChats={() => openSystems("library:chats")} />}
            {DESIGN === "classic" && <ConstellationClassic graph={graph} state={constellationState} cited={lastCited.documents} activeChat={conversationId} onOpenChat={openSavedChat} onOpenChats={() => openSystems("library:chats")} />}

            <section className="hud-center" aria-label="June’s state">
              <div className="hud-orb-space" aria-hidden="true" />
              {todayNotice && <div className="today-notice" role="status"><span>{todayNotice.phrase}</span><button type="button" className="quiet-button" onClick={() => { settleToday(todayNotice.key); setTodayNotice(null); }}>Dismiss</button></div>}
              <div className="hud-chips">{(() => { const next = timers.state?.timers.filter(t => t.status === "active").sort((x, y) => x.endsAt - y.endsAt)[0]; return next && timers.state ? <TimerChip timer={next} serverNow={timers.state.serverNow} receivedAt={timers.receivedAt} onOpen={() => openSystems("timers")} /> : null; })()}
                {!specimen && <><span className="hud-chip hud-lock" key={orb.mood} title={orb.label}><span className="hud-dot" />{stateWord}</span>
                <span className={`hud-chip${status?.state === "ready" ? "" : " is-amber"}`}><span aria-hidden="true">◆</span>{status?.state === "ready" ? modelShort : "Model offline"}<span aria-hidden="true" className="hud-bolt">⚡</span>local</span></>}
              </div>
              <div className="hud-tool hud-lock" key={toolLine}><span className="hud-dot" /><span className="hud-caret">{toolLine}{busy && !writing && <Elapsed since={waitSince} />}</span></div>
              {specimen ? <Subtitles caption={caption} start={captionStart} end={captionEnd} quiet={!(lastJune && !busy)}
                fallback={busy && lastUser ? `“${lastUser.length > 140 ? lastUser.slice(0, 139) + "…" : lastUser}”` : lastJune && !busy ? (lastJune.length > 240 ? lastJune.slice(0, 239) + "…" : lastJune) : handsFree.active ? "Say “Hey June”, or type below." : "Type below, or enable hands-free and say “Hey June”."} />
              : <p className="hud-caption" aria-hidden="true">
                {caption ? <><span className="is-done">{caption.slice(0, captionStart)}</span><span className="is-now">{caption.slice(captionStart, captionEnd)}</span><span className="is-todo">{caption.slice(captionEnd)}</span></>
                  : busy && lastUser ? <span className="is-todo">“{lastUser.length > 120 ? lastUser.slice(0, 119) + "…" : lastUser}”</span>
                  : <span className="is-todo">{handsFree.active ? "Say “Hey June”, or type below." : "Type below, or enable hands-free and say “Hey June”."}</span>}
              </p>}
              <div className="hud-clusters" role="group" aria-label="Parts of June">
                {clusterInfo.map((item, i) => <button key={item.name} type="button" className={`hud-cluster${chipFocus === i ? " is-on" : ""}`} aria-label={`${item.name}: ${item.value}`}
                  onPointerEnter={event => { if (event.pointerType === "mouse") setChipFocus(i); }} onPointerLeave={() => setChipFocus(-1)} onFocus={() => setChipFocus(i)} onBlur={() => setChipFocus(-1)}
                  onClick={() => { if (clusterSection[i]) openSystems(clusterSection[i]); }}><span className="hud-swatch" style={{ background: rgb(CLUSTER_RGB[i]) }} />{item.name}</button>)}
              </div>
            </section>

            {!specimen && <section className="hud-telemetry" aria-label="Telemetry">
              <div className="hud-panel">
                <div className="hud-label">Parameters</div>
                <div className="hud-stat-big"><Counter value={status?.state === "ready" ? status.parameters ?? null : null} /></div>
                <div className="hud-stats">
                  <div><div className="hud-label">Cost · local</div><span className="hud-big" aria-label="No cost: runs on this Mac">$0</span></div>
                  <div><div className="hud-label">Memories</div><Counter value={memoryCount} /></div>
                  <div><div className="hud-label">Documents</div><Counter value={readyDocuments.length} /></div>
                  <div><div className="hud-label">Chats</div><Counter value={chatCount} /></div>
                </div>
              </div>
              <div className="hud-rows">
                <button type="button" className="hud-row" aria-pressed={handsFree.active} disabled={!handsFree.active && !handsFreeEnabled} title={!handsFree.active && !handsFreeEnabled ? "Hands-free needs June’s voice and local model to be ready" : undefined} onClick={() => handsFree.active ? handsFree.stop() : startHandsFree()}><span>Ears · hands-free</span><span className={handsFree.active ? "is-on" : "is-off"}>{handsFree.active ? "on" : "off"}</span></button>
                <button type="button" className="hud-row" aria-pressed={voice.speakReplies} onClick={() => voice.setSpeakReplies(!voice.speakReplies)}><span>Voice · Heart</span><span className={voice.speakReplies ? "is-on" : "is-off"}>{voice.speakReplies ? "on" : "muted"}</span></button>
                <button type="button" className="hud-row" onClick={() => openSystems("library")}><span>Memory</span><span className={library.temporary ? "is-off" : "is-on"}>{library.temporary ? "temporary" : "saved"}</span></button>
                <div className="hud-row is-static"><span>Cloud</span><span className="is-amber">off · local only</span></div>
              </div>
              <div className="hud-panel hud-last">
                <div className="hud-label">Last reply</div>
                <dl><dt>retrieval</dt><dd>{seconds(lastReply?.retrieval)}</dd><dt>answer</dt><dd>{seconds(lastReply?.answer ?? lastReply?.total)}</dd><dt>first audio</dt><dd>{seconds(firstAudio)}</dd></dl>
              </div>
            </section>}
          </div>
        </section>

        <section className="hud-dialogue" aria-label="Conversation">
          <JobQuestionCard active={integrations.plans.some(p => (p.status === "approved" || p.status === "running") && p.steps.some(s => s.capability === "jobs.apply"))} onAnnounce={setAnnouncement} />
          {specimen ? <aside id="june-history" className={`june-history${historyOpen ? " is-open" : ""}`} aria-label="Conversation history" inert={!historyOpen}>
            <div className="june-history-head"><span className="hud-label">History</span><button type="button" className="quiet-button" onClick={() => { setHistoryOpen(false); historyToggle.current?.focus(); }}>Close</button></div>
            {conversationLog}
          </aside> : conversationLog}

          {specimen && <button ref={historyToggle} type="button" className="june-history-toggle" aria-expanded={historyOpen} aria-controls="june-history" onClick={() => setHistoryOpen(open => !open)}>History{messages.length > 0 && <span className="cin-count">{Math.ceil(messages.length / 2)}</span>}</button>}
          <div className="composer-area hud-composer">
            <label htmlFor="message" className="hud-label">Message June</label>
            {contextLimited && <p className="demo-notice" role="status">Long conversation · June uses recent messages to fit her local model. Older messages remain visible but may be outside her current context. This is not saved memory.</p>}
            {error && <div className="error-notice" role="alert">{error}</div>}
            <form className="composer hud-panel" onSubmit={event => { event.preventDefault(); void send(); }}>
              <textarea ref={composer} id="message" value={draft} maxLength={MAX_MESSAGE_LENGTH} rows={3} placeholder="Ask, or say “Hey June”…" disabled={busy || ((!library.data || !!library.error) && !library.temporary)} onChange={event => setDraft(event.target.value)} onKeyDown={event => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); }
              }} />
              <button type="button" className={`hud-mic${handsFree.active ? " is-live" : ""}`} aria-label={handsFree.active ? "Stop hands-free" : "Start hands-free"} aria-pressed={handsFree.active} disabled={!handsFree.active && !handsFreeEnabled} onClick={() => handsFree.active ? handsFree.stop() : startHandsFree()}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg></button>
              {busy ? <button className="send-button stop-button" type="button" onClick={stopAll}><span aria-hidden="true">■</span><span className="sr-only">Stop</span></button> : <button className="send-button" type="submit" aria-label="Send" disabled={modelChanging || !draft.trim() || voice.recognition.phase !== "idle" || ((!library.data || !!library.error) && !library.temporary)}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg></button>}
            </form>
            <div className="composer-notes"><span>Enter to send · Shift + Enter for a new line</span><span>{timing || `${draft.length}/${MAX_MESSAGE_LENGTH}`}</span></div>
          </div>
        </section>
      </main>

      <div className={`hud-scrim${systemsOpen ? " is-open" : ""}`} aria-hidden="true" onClick={closeSystems} />
      <aside ref={drawer} id="systems" className={`hud-drawer${systemsOpen ? " is-open" : ""}`} role="dialog" aria-modal="true" aria-label="Systems" tabIndex={-1} inert={!systemsOpen}>
        <div className="hud-drawer-head"><span className="hud-label">Systems</span>
          <nav aria-label="Systems sections">{[["documents", "Documents"], ["library", "Memory & chats"], ["daily", "Daily"], ["handsfree", "Hands-free"], ["hands", "Hands"], ["integrations", "Integrations"], ["mail", "Email & jobs"], ["shopping", "Shopping"], ["screen", "Screen"], ["timers", "Timers"], ["reminders", "Reminders"], ["voice", "Voice"], ["model", "Model"], ["lab", "Orb & sound"]].map(([id, label]) => <button key={id} type="button" className="hud-tab" onClick={() => openSystems(id)}>{label}</button>)}</nav>
          <button type="button" className="quiet-button" onClick={closeSystems}>Close</button></div>
        <div className="hud-drawer-body" inert={modelChanging}>
          <div id="systems-documents"><DocumentsPanel data={documents}/><CreationsPanel refreshKey={messages.length} onAnnounce={setAnnouncement} /></div>
          <div id="systems-library"><LibraryPanel request={libraryTab} openGeneration={conversationOpenGeneration} onDeleteActive={()=>newChat()} library={library} activeId={conversationId} onOpen={openConversation} /></div>
          <div id="systems-reminders"><RemindersPanel reminders={reminders} onHear={phrase => voice.replay(phrase)} onAnnounce={setAnnouncement} /></div>
          <div id="systems-timers"><TimersPanel timers={timers} onHear={phrase => voice.replay(phrase)} onAnnounce={setAnnouncement} /></div>
          <div id="systems-hands"><HandsPanel actions={actions} onAnnounce={setAnnouncement} /></div>
          <div id="systems-daily"><DailyPanel daily={daily} integrations={integrations} onHear={phrase => voice.replay(phrase)} onAnnounce={setAnnouncement} /></div>
          <div id="systems-integrations"><IntegrationsPanel integrations={integrations} onAnnounce={setAnnouncement} onForgotten={() => void actions.refresh()} />
            <div className="timers-panel integrations-panel"><CommandsPanel plans={integrations.plans} onPlan={integrations.upsert} onAnnounce={setAnnouncement} /></div></div>
          <div id="systems-mail"><MailJobsPanel plans={integrations.plans} onPlan={integrations.upsert} onAnnounce={setAnnouncement} /></div>
          <div id="systems-shopping"><TransactionsPanel plans={integrations.plans} capabilities={integrations.capabilities ?? []} serverNow={integrations.serverNow} receivedAt={integrations.receivedAt}
            onPlan={integrations.upsert} onRefreshPlans={() => void integrations.refreshPlans()} onAnnounce={setAnnouncement} /></div>
          <div id="systems-screen"><ScreenPanel onAnnounce={setAnnouncement} /></div>
          <div id="systems-handsfree"><HandsFreePanel controls={handsFree} enabled={handsFreeEnabled} onStart={startHandsFree} />
          {handsFree.active && <button className="quiet-button all-stop" onClick={stopAll}>Stop conversation &amp; microphone</button>}</div>
          <div id="systems-voice"><VoicePanel voice={voice} busy={busy || modelChanging} onUse={useTranscript} onActivate={() => { cancelExtraction(); setPreview("auto"); }} />
          {(voice.recognition.phase !== "idle" || voice.speech.phase !== "idle") && !busy && <button className="quiet-button all-stop" onClick={stopAll}>Stop all voice activity</button>}</div>
          <div id="systems-model">
            <div className="connection-bar">
              <div className="connection-copy"><span className={`status-dot ${status?.state === "ready" ? "ready" : "offline"}`} /><span><strong>{status?.model || "Local AI"}</strong><span className="connection-description">{connection}</span></span></div>
              <button className="quiet-button" disabled={busy} onClick={() => void reconnect()}>Reconnect</button>
            </div>
            <ModelPicker activeModel={status?.model} changing={modelChanging}
              disabled={busy || handsFree.active || speechBusy || recordingBusy || audio.phase !== "idle"}
              onChanging={value => { modelChangingRef.current=value; setModelChanging(value); if(value) cancelExtraction(); }}
              onChanged={() => { cancelExtraction(); voice.cancel(); audio.stop(); setTiming(""); void reconnect(); }} />
          </div>
          <div id="systems-lab"><OrbControls preview={preview} onPreview={setPreview} still={still} onStill={setStill} disabled={busy || handsFree.active} />
          <details className="sound-workshop"><summary>Sound &amp; microphone <span>{audio.phase === "listening" ? "Microphone active" : audio.phase === "playing" ? "Audio playing" : audio.phase === "requesting" ? "Permission pending" : audio.phase === "paused" ? "Paused" : "Explore audio reactivity"}</span></summary>{voice.engine === "native" && <p className="handsfree-note">Enable manual browser recording above to use this workshop’s microphone.</p>}<AudioPanel audio={audio} disableCapture={!voice.browserCapture || busy || voice.recognition.phase !== "idle"} onActivate={() => { cancelExtraction(); handsFree.stop(); voice.cancel(); setPreview("auto"); }} /></details>
          <p className="handsfree-note"><a href="/learn/phase-7">Inside document questions ↗</a></p></div>
        </div>
      </aside>

      <footer className="footer hud-footer"><p>Local wake phrase · Whisper &amp; Qwen · June’s local Heart voice.</p><p>Approved memories only. June can make mistakes.</p></footer>
      <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
      <span className="sr-only" role="status" aria-live="polite">{orb.label}</span>
    </div>
  );
}
