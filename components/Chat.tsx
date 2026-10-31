"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatEvent, ChatMessage, ChatMode, ModelStatus } from "@/lib/chat-types";
import { MAX_MESSAGE_LENGTH } from "@/lib/chat-types";
import { JUNE_VERSION } from "@/lib/version";
import { readJsonLines } from "@/lib/ndjson";
import { prepareContext } from "@/lib/context";

import Orb from "./orb/Orb";
import AudioPanel from "./orb/AudioPanel";
import OrbControls from "./orb/OrbControls";
import { useAudio } from "./orb/useAudio";
import { resolveOrb, type Preview } from "@/lib/orb/state";

import { useVoice } from "./voice/useVoice";
import VoicePanel from "./voice/VoicePanel";
import ReplyStatus from "./voice/ReplyStatus";
import { useHandsFree } from "./voice/useHandsFree";
import HandsFreePanel, { handsFreeLabels } from "./voice/HandsFreePanel";
import { mergeTranscript } from "@/lib/voice/sentences";

import LibraryPanel from "./memory/LibraryPanel";
import { useLibrary } from "./memory/useLibrary";
import { libraryRequest, LibraryError, type SavedConversation } from "@/lib/memory-types";

type DisplayMessage = ChatMessage & { id: string; state?: "pending" | "complete" | "stopped" | "failed"; limited?: boolean; repetitionStopped?: boolean; memoryIds?: string[] };

export default function Chat() {
  const audio = useAudio();
  const manualTakeover = useRef<() => void>(() => {});
  const voice = useVoice(audio.stop, () => manualTakeover.current());
  const [preview, setPreview] = useState<Preview>("auto");
  const [still, setStill] = useState(false);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<ChatMode>("local");
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [timing, setTiming] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [contextLimited, setContextLimited] = useState(false);
  const history = useRef<ChatMessage[]>([]);
  const active = useRef<AbortController | null>(null);
  const requestId = useRef(0);
  const busyRef = useRef(false);
  const composer = useRef<HTMLTextAreaElement>(null);
  const conversation = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const spokenTurn = useRef<{ turn: number; request: number; complete: boolean } | null>(null);

  const [conversationId, setConversationId] = useState<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const extraction = useRef<AbortController | null>(null);
  const [suggestAfter, setSuggestAfter] = useState<{conversationId:string;turnId:string}|null>(null);
  const library = useLibrary(() => {
    interrupt(); handsFree.stop(); voice.cancel(); audio.stop(); history.current=[];
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
  function interrupt() {
    cancelExtraction();
    spokenTurn.current = null;
    requestId.current++;
    active.current?.abort(); active.current = null;
    busyRef.current = false; setBusy(false);
    voice.stopVoice("voice-turn-cancelled");
    setMessages(previous => previous.map(message => message.state === "pending" ? { ...message, state: "stopped" } : message));
  }
  const handsFree = useHandsFree({
    wake: () => { interrupt(); setPreview("auto"); },
    transcript: (content, turn) => { void send({ content, voiceTurn: turn }); },
    cancel: interrupt,
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

  const speechBusy = voice.speech.phase !== "idle";
  const recordingBusy = voice.recognition.phase !== "idle" || ["requesting","preparing","listening","transcribing","connecting"].includes(handsFree.state.phase);
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
    const stop = () => { interrupt(); voice.cancel(); audio.stop(); handsFree.stop(); };
    const hide = () => {if(document.hidden)stop();};
    window.addEventListener("pagehide",stop);document.addEventListener("visibilitychange",hide);
    return () => {extraction.current?.abort();window.removeEventListener("pagehide",stop);document.removeEventListener("visibilitychange",hide);};
  },[]);
  useEffect(() => {voice.setExpression(library.temporary ? "steady" : library.data?.profile.expression || "steady");},[library.data?.profile.expression,library.temporary]);

  function openConversation(chat:SavedConversation) {
    newChat();setConversationId(chat.id);conversationIdRef.current=chat.id;
    setMessages(chat.turns.flatMap(t => [{role:"user" as const,content:t.user,id:`user-${t.id}`},{role:"assistant" as const,content:t.assistant,id:`assistant-${t.id}`,state:t.status === "pending" ? "stopped" as const : t.status,memoryIds:JSON.parse(t.memories || "[]")}]));
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

  function newChat(nextMode = mode) {
    cancelExtraction(); setConversationId(null);conversationIdRef.current=null;
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
    setTiming("");
    setMode(nextMode);
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
    if (!content || busyRef.current || voice.recognition.phase !== "idle" || content.length > MAX_MESSAGE_LENGTH) return;
    if ((!library.data || library.error) && !library.temporary) {setError("Private storage is unavailable. Retry storage or explicitly choose temporary chat.");return;}
    cancelExtraction();
    setPreview("auto");
    busyRef.current = true;
    setBusy(true);
    setError("");
    setTiming("");
    if (!input) setDraft("");
    const id = ++requestId.current;
    spokenTurn.current = input?.voiceTurn !== undefined ? { turn: input.voiceTurn, request: id, complete: false } : null;
    voice.begin(id, automatic, automatic ? { voiceSessionId, turnId: input!.voiceTurn! } : undefined);
    const controller = new AbortController();
    active.current = controller;
    const user: ChatMessage = { role: "user", content };
    const assistantId = `assistant-${id}`;
    const prepared = prepareContext(history.current, user);
    const context = prepared.messages;
    if (prepared.limited) setContextLimited(true);
    const started = performance.now();
    let firstToken = 0;
    let reply = "";
    let complete = false;
    let replyLimited = false;
    let repetitionStopped = false;
    const stageTimings: Record<string, number> = {};
    let memoryIds: string[] = [];
    const turnId=crypto.randomUUID();
    let savedConversation=conversationIdRef.current;
    nearBottom.current = true;
    setMessages(previous => [...previous,
      { ...user, id: `user-${id}` },
      { role: "assistant", content: "", id: assistantId, state: "pending" },
    ]);
    setAnnouncement("June is preparing a reply.");

    // React state drives the screen; successful message pairs drive model context.
    // Failed or stopped replies stay visible but never become hidden context.
    const update = (state: DisplayMessage["state"]) => {
      if (id !== requestId.current) return;
      setMessages(previous => previous.map(message => message.id === assistantId
        ? { ...message, content: reply, state, limited: replyLimited, repetitionStopped, memoryIds } : message));
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
        body: JSON.stringify({ mode, messages: context, ...(library.temporary ? {temporary:true} : {conversationId:savedConversation,turnId}) }),
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
            console.debug('[June timing]', JSON.stringify({ event: 'first-text', at: Date.now(), ...(automatic ? { voiceSessionId, turnId: input!.voiceTurn! } : {}), durationMs: firstToken - started }));
          }
          reply += event.text;
          voice.push(id, event.text);
          update("pending");
        } else if (event.type === "done" && typeof event.model === "string") {
          complete = true;
          replyLimited = event.limited === true;
          repetitionStopped = event.repetitionStopped === true;
          if (repetitionStopped) { spokenTurn.current = null; voice.stopVoice('repetition-stopped'); }
          memoryIds = Array.isArray(event.memoryIds) ? event.memoryIds : [];
          if(!library.temporary && event.persistence!=="saved") throw new Error("This reply was not confirmed saved. Check private storage.");
          break;
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
      if (!repetitionStopped) voice.finish(id, !replyLimited);
      if (!repetitionStopped) history.current = [...context, { role: "assistant", content: reply }];
      update("complete");
      void library.refresh();
      if(!repetitionStopped && mode==="local" && !library.temporary && savedConversation) setSuggestAfter({conversationId:savedConversation,turnId});
      const elapsed = ((performance.now() - started) / 1000).toFixed(1);
      const first = ((firstToken - started) / 1000).toFixed(1);
      setTiming(`${elapsed}s total · first text in ${first}s${Object.entries(stageTimings).map(([stage, ms]) => ` · ${stage} ${(ms / 1000).toFixed(1)}s`).join('')}`);
      if (repetitionStopped && automatic) handsFree.stop("June stopped a repeated reply. Retry manually when you’re ready.");
      setAnnouncement(repetitionStopped ? "Repeated reply stopped. The text is preserved; retry manually." : replyLimited ? "June reached the reply length limit. Ask her to continue." : "June’s reply is complete.");
    } catch (failure) {
      if (id !== requestId.current) return;
      voice.stopVoice();
      if (controller.signal.aborted) {
        update("stopped");
        setAnnouncement("Reply stopped. You can send another message.");
      } else {
        update("failed");
        setError(failure instanceof Error ? failure.message : "June could not finish this reply.");
        if (!input) setDraft(content);
        setAnnouncement(automatic ? "Voice reply failed. Your typed draft is unchanged." : "Reply failed. Your message is back in the input so you can retry.");
        if (mode === "local") void reconnect();
      }
      if (automatic) handsFree.stop(controller.signal.aborted ? "" : "The local reply failed. Check June’s connection, then enable hands-free again.");
    } finally {
      if (id === requestId.current) {
        active.current = null;
        busyRef.current = false;
        setBusy(false);
        if (!input) composer.current?.focus();
      }
    }
  }

  const voiceActivity = { listening: voice.recognition.phase === "listening", speaking: voice.speech.phase === "speaking", requesting: voice.recognition.phase === "requesting", finishing: voice.recognition.phase === "finishing" };
  const automatic = handsFree.state.phase;
  const orb = handsFree.active ? {
    mood: handsFree.state.probing ? "listening" as const : voiceActivity.speaking ? "speaking" as const : ["listening", "followup"].includes(automatic) ? "listening" as const : ["generating", "transcribing", "connecting", "preparing", "requesting"].includes(automatic) ? "thinking" as const : "idle" as const,
    label: handsFree.state.probing ? "Checking microphone sound · voice paused" : voiceActivity.speaking ? "June is speaking · speak to interrupt" : handsFreeLabels[automatic],
  } : resolveOrb(busy, mode === "demo", preview, audio.phase, voiceActivity);
  const stopAll = () => { handsFree.stop(); interrupt(); voice.cancel(); audio.stop(); setAnnouncement("Stopped. Microphone off; ready for another message."); };
  function useTranscript(text: string) {
    const merged = mergeTranscript(draft, text);
    if (merged.length > MAX_MESSAGE_LENGTH) { setError("The combined message is too long. Shorten your draft or transcript before adding it."); return; }
    setDraft(merged); voice.clearTranscript(); setError(""); composer.current?.focus();
  }
  const connection = mode === "demo" ? "Practice mode · simulated replies" : status?.message || "Connecting to your local model…";
  return (
    <div className="chat-page">
      <header className="masthead">
        <a className="wordmark" href="/" aria-label="June home"><span className="brand-dot" />june</a>
        <div className="header-actions"><span className="version">June v{JUNE_VERSION}</span><button className="quiet-button" onClick={() => newChat()}>New chat</button></div>
      </header>

      <main className="chat-shell">
        <section className="face-section" aria-labelledby="june-title">
          <div className="face-copy"><p className="eyebrow">Phase 6 · Memory and personality</p><h1 id="june-title">A little more<br /><em>personal.</em></h1><p className="subtitle">A familiar voice. A memory you approve. A conversation to return to.</p><a className="learn-link" href="/learn/phase-6">Inside memory and personality <span aria-hidden="true">↗</span></a><OrbControls preview={preview} onPreview={setPreview} still={still} onStill={setStill} disabled={busy || handsFree.active} /></div>
          <Orb expression={library.temporary ? "steady" : library.data?.profile.expression} mood={orb.mood} label={orb.label} level={voice.engine === "native" && voice.speech.phase === "speaking" ? voice.activity : handsFree.active ? handsFree.level : voice.recognition.phase === "listening" ? voice.level : audio.level} still={still} activity={voice.engine === "browser" ? voice.activity : undefined} speechActive={voice.engine === "browser" && voice.speech.phase === "speaking" && !handsFree.state.probing} />
        </section>
        <LibraryPanel onDeleteActive={()=>newChat()} library={library} activeId={conversationId} onOpen={openConversation} />
        <HandsFreePanel controls={handsFree} enabled={voice.engine === 'native' && !!voice.ownerId && !busy && (!!library.data && !library.error || library.temporary) && mode === "local" && status?.state === "ready" && voice.speakReplies && !!voice.choices.selected && voice.support.recognition} onStart={() => { cancelExtraction(); audio.stop(); voice.cancel(); setPreview("auto"); handsFree.start(); }} />
        {handsFree.active && <button className="quiet-button all-stop" onClick={stopAll}>Stop conversation &amp; microphone</button>}
        <VoicePanel voice={voice} busy={busy} onUse={useTranscript} onActivate={() => { cancelExtraction(); setPreview("auto"); }} />
        {(voice.recognition.phase !== "idle" || voice.speech.phase !== "idle") && !busy && <button className="quiet-button all-stop" onClick={stopAll}>Stop all voice activity</button>}
        <details className="sound-workshop"><summary>Sound &amp; microphone <span>{audio.phase === "listening" ? "Microphone active" : audio.phase === "playing" ? "Audio playing" : audio.phase === "requesting" ? "Permission pending" : audio.phase === "paused" ? "Paused" : "Explore audio reactivity"}</span></summary>{voice.engine === "native" && <p className="handsfree-note">Choose browser audio above to use this workshop’s microphone.</p>}<AudioPanel audio={audio} disableCapture={voice.engine !== "browser" || busy || voice.recognition.phase !== "idle"} onActivate={() => { cancelExtraction(); handsFree.stop(); voice.cancel(); setPreview("auto"); }} /></details>

        <div className="connection-bar">
          <div className="connection-copy"><span className={`status-dot ${mode === "demo" ? "demo" : status?.state === "ready" ? "ready" : "offline"}`} /><span><strong>{mode === "demo" ? "Simulated demo" : status?.model || "Local AI"}</strong><span className="connection-description">{connection}</span></span></div>
          <div className="connection-actions"><label className="sr-only" htmlFor="mode">Reply source</label><select id="mode" value={mode} disabled={busy} onChange={event => newChat(event.target.value as ChatMode)}><option value="local">Local AI</option><option value="demo">Practice demo</option></select>{mode === "local" && <button className="quiet-button" disabled={busy} onClick={() => void reconnect()}>Reconnect</button>}</div>
        </div>
        {mode === "demo" && <p className="demo-notice">Practice demo: these replies are simulated. Choose Local AI for real model answers.</p>}

        <div ref={conversation} className="conversation" role="log" aria-label="Conversation with June" aria-live="off" onScroll={() => {
          const panel = conversation.current;
          if (panel) nearBottom.current = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 100;
        }}>
          {!messages.length && <div className="empty-state"><span className="empty-label">A BEGINNING, WITH ROOM TO GROW</span><h2>Hello, I’m <em>June.</em></h2><p>Ask a question, explore an idea, or just say hello.</p><div className="suggestions">{["Introduce yourself, June.", "Explain async/await simply."].map(text => <button key={text} onClick={() => { setDraft(text); composer.current?.focus(); }}>{text}<span aria-hidden="true">↗</span></button>)}</div></div>}
          {messages.map(message => <article key={message.id} className={`message ${message.role}`} aria-label={message.role === "user" ? "Your message" : "June’s message"}><span className="message-label">{message.role === "user" ? "YOU" : "JUNE"}</span><div className="message-text">{message.content || (message.state === "pending" ? <span className="waiting">Thinking<span aria-hidden="true">…</span></span> : message.state === "stopped" ? "Reply stopped." : "No reply yet.")}</div><ReplyStatus state={message.state} hasContent={!!message.content} limited={message.limited} repetitionStopped={message.repetitionStopped} busy={busy} onRetry={() => {
            const index = messages.findIndex(item => item.id === message.id);
            const question = messages[index - 1];
            if (question?.role === 'user') void send({ content: question.content });
          }} />{message.role === "assistant" && !!message.memoryIds?.length && <details className="used-memories"><summary>Approved facts provided ({message.memoryIds.length})</summary>{message.memoryIds.map(mid=><p key={mid}>{library.data?.memories.find(m=>m.id===mid)?.text || "This saved memory has since been removed."}</p>)}</details>}{message.role === "assistant" && message.state === "complete" && !message.repetitionStopped && <button className="quiet-button hear-reply" disabled={busy || !voice.choices.selected} onClick={() => { setPreview("auto"); voice.replay(message.content); }}>Hear reply</button>}</article>)}
        </div>

        <div className="composer-area">
          {contextLimited && <p className="demo-notice" role="status">Long conversation · June uses recent messages to fit her local model. Older messages remain visible but may be outside her current context. This is not saved memory.</p>}
          {error && <div className="error-notice" role="alert">{error}</div>}
          <form className="composer" onSubmit={event => { event.preventDefault(); void send(); }}>
            <label htmlFor="message" className="sr-only">Message June</label>
            <textarea ref={composer} id="message" value={draft} maxLength={MAX_MESSAGE_LENGTH} rows={2} placeholder="What’s on your mind?" disabled={busy || ((!library.data || !!library.error) && !library.temporary)} onChange={event => setDraft(event.target.value)} onKeyDown={event => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); }
            }} />
            {busy ? <button className="send-button stop-button" type="button" onClick={stopAll}><span aria-hidden="true">■</span> Stop</button> : <button className="send-button" type="submit" disabled={!draft.trim() || voice.recognition.phase !== "idle" || ((!library.data || !!library.error) && !library.temporary)}><span>Send</span><span aria-hidden="true">↑</span></button>}
          </form>
          <div className="composer-notes"><span>Enter to send · Shift + Enter for a new line</span><span>{timing || `${draft.length}/${MAX_MESSAGE_LENGTH}`}</span></div>
        </div>
      </main>

      <footer className="footer"><p>Local wake phrase · Whisper &amp; Qwen · your selected system voice.</p><p>Approved memories only. June can make mistakes.</p></footer>
      <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
    </div>
  );
}
