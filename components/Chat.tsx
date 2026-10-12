"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatEvent, ChatMessage, ChatMode, ModelStatus } from "@/lib/chat-types";
import { MAX_MESSAGE_LENGTH } from "@/lib/chat-types";
import { readJsonLines } from "@/lib/ndjson";

import Orb from "./orb/Orb";
import AudioPanel from "./orb/AudioPanel";
import OrbControls from "./orb/OrbControls";
import { useAudio } from "./orb/useAudio";
import { resolveOrb, type Preview } from "@/lib/orb/state";

type DisplayMessage = ChatMessage & { id: string; state?: "pending" | "complete" | "stopped" | "failed" };

export default function Chat() {
  const audio = useAudio();
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
  const history = useRef<ChatMessage[]>([]);
  const active = useRef<AbortController | null>(null);
  const requestId = useRef(0);
  const busyRef = useRef(false);
  const composer = useRef<HTMLTextAreaElement>(null);
  const conversation = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);

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
    audio.stop(); setPreview("auto");
    requestId.current += 1;
    active.current?.abort();
    active.current = null;
    history.current = [];
    busyRef.current = false;
    setBusy(false);
    setMessages([]);
    setDraft("");
    setError("");
    setTiming("");
    setMode(nextMode);
    setAnnouncement("New chat. Previous conversation cleared.");
    nearBottom.current = true;
    composer.current?.focus();
  }

  async function send() {
    const content = draft.trim();
    if (!content || busyRef.current || content.length > MAX_MESSAGE_LENGTH) return;
    setPreview("auto");
    busyRef.current = true;
    setBusy(true);
    setError("");
    setTiming("");
    setDraft("");
    const id = ++requestId.current;
    const controller = new AbortController();
    active.current = controller;
    const user: ChatMessage = { role: "user", content };
    const assistantId = `assistant-${id}`;
    const context = [...history.current, user];
    const started = performance.now();
    let firstToken = 0;
    let reply = "";
    let complete = false;
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
        ? { ...message, content: reply, state } : message));
    };
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, messages: context }),
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
          if (!firstToken) firstToken = performance.now();
          reply += event.text;
          update("pending");
        } else if (event.type === "done" && typeof event.model === "string") {
          complete = true;
          break;
        } else if (event.type === "error" && typeof event.message === "string") {
          throw new Error(event.message);
        } else throw new Error("June sent an invalid update.");
      }
      controller.signal.throwIfAborted();
      if (id !== requestId.current) return;
      if (!complete || !reply.trim()) throw new Error("The reply ended unexpectedly. Please try again.");
      history.current = [...context, { role: "assistant", content: reply }];
      update("complete");
      const elapsed = ((performance.now() - started) / 1000).toFixed(1);
      const first = ((firstToken - started) / 1000).toFixed(1);
      setTiming(`${elapsed}s total · first text in ${first}s`);
      setAnnouncement("June’s reply is complete.");
    } catch (failure) {
      if (id !== requestId.current) return;
      if (controller.signal.aborted) {
        update("stopped");
        setAnnouncement("Reply stopped. You can send another message.");
      } else {
        update("failed");
        setError(failure instanceof Error ? failure.message : "June could not finish this reply.");
        setDraft(content);
        setAnnouncement("Reply failed. Your message is back in the input so you can retry.");
        if (mode === "local") void reconnect();
      }
    } finally {
      if (id === requestId.current) {
        active.current = null;
        busyRef.current = false;
        setBusy(false);
        composer.current?.focus();
      }
    }
  }

  const orb = resolveOrb(busy, mode === "demo", preview, audio.phase);
  const connection = mode === "demo" ? "Practice mode · simulated replies" : status?.message || "Connecting to your local model…";
  return (
    <div className="chat-page">
      <header className="masthead">
        <a className="wordmark" href="/" aria-label="June home"><span className="brand-dot" />june</a>
        <div className="header-actions"><span className="version">June v0.2</span><button className="quiet-button" onClick={() => newChat()}>New chat</button></div>
      </header>

      <main className="chat-shell">
        <section className="face-section" aria-labelledby="june-title">
          <div className="face-copy"><p className="eyebrow">Phase 2 · June gets a face</p><h1 id="june-title">A little spark.<br />A little more <em>June.</em></h1><p className="subtitle">A living network, moving with your conversation.</p><a className="learn-link" href="/learn/phase-2">Explore how her orb works <span aria-hidden="true">↗</span></a><OrbControls preview={preview} onPreview={setPreview} still={still} onStill={setStill} disabled={busy} /></div>
          <Orb mood={orb.mood} label={orb.label} level={audio.level} still={still} />
        </section>
        <details className="sound-workshop"><summary>Sound &amp; microphone <span>{audio.phase === "listening" ? "Microphone active" : audio.phase === "playing" ? "Audio playing" : audio.phase === "requesting" ? "Permission pending" : audio.phase === "paused" ? "Paused" : "Explore audio reactivity"}</span></summary><AudioPanel audio={audio} onActivate={() => setPreview("auto")} /></details>

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
          {messages.map(message => <article key={message.id} className={`message ${message.role}`} aria-label={message.role === "user" ? "Your message" : "June’s message"}><span className="message-label">{message.role === "user" ? "YOU" : "JUNE"}</span><div className="message-text">{message.content || (message.state === "pending" ? <span className="waiting">Thinking<span aria-hidden="true">…</span></span> : message.state === "stopped" ? "Reply stopped." : "No reply yet.")}</div>{message.state === "stopped" && message.content && <span className="message-note">Stopped · partial reply</span>}{message.state === "failed" && <span className="message-note">Not completed · message restored below</span>}</article>)}
        </div>

        <div className="composer-area">
          {error && <div className="error-notice" role="alert">{error}</div>}
          <form className="composer" onSubmit={event => { event.preventDefault(); void send(); }}>
            <label htmlFor="message" className="sr-only">Message June</label>
            <textarea ref={composer} id="message" value={draft} maxLength={MAX_MESSAGE_LENGTH} rows={2} placeholder="What’s on your mind?" disabled={busy} onChange={event => setDraft(event.target.value)} onKeyDown={event => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); }
            }} />
            {busy ? <button className="send-button stop-button" type="button" onClick={() => active.current?.abort()}><span aria-hidden="true">■</span> Stop</button> : <button className="send-button" type="submit" disabled={!draft.trim()}><span>Send</span><span aria-hidden="true">↑</span></button>}
          </form>
          <div className="composer-notes"><span>Enter to send · Shift + Enter for a new line</span><span>{timing || `${draft.length}/${MAX_MESSAGE_LENGTH}`}</span></div>
        </div>
      </main>

      <footer className="footer"><p>On your Mac. In this conversation.</p><p>No saved memory yet. June can make mistakes.</p></footer>
      <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
    </div>
  );
}
