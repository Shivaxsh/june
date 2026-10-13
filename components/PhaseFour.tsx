"use client";

import { useEffect, useRef, useState } from "react";

const topics = ["Python basics", "pip & environments", "Jupyter notebooks", "Async Python", "FastAPI & WebSockets"];
const descriptions = [
  "Variables name values. Lists collect them. Loops repeat work, functions package a task, and classes keep related state and behaviour together. These are the building blocks behind June’s new backend.",
  "pip installs Python packages. A virtual environment gives this project its own packages without changing your Mac’s Python installation. June’s exact installed versions are saved in a dependency lock.",
  "A notebook lets you run small cells and inspect their results. Use it to explore Python before changing June’s live service. Jupyter is optional for running June; the included notebook needs no model or private data.",
  "await lets Python wait for an answer without blocking other network work. Cancellation matters just as much: a stopped request closes its model connection, or terminates its speech process, before releasing resources.",
  "FastAPI defines the server’s entry points. Normal chat streams over HTTP; this lab uses a WebSocket to carry requests, reply events and a Stop message over one connection. Both reach the same local model adapter.",
];
const snippets = [
  'name = "June"\nskills = ["chat", "transcribe", "speak"]\n\ndef describe(name, skills):\n    return f"{name} has {len(skills)} skills"\n\nfor skill in skills:\n    print(skill)\n\nclass Assistant:\n    def __init__(self, name):\n        self.name = name\n\nprint(describe(name, skills))',
  '# Run these from the June project folder.\npython3 -m venv backend/.venv\nbackend/.venv/bin/python -m pip install -r backend/requirements.lock\n\n# June wraps the same steps for you:\nnpm run backend:setup\nnpm start\n\n# Check the running backend and local engines:\nnpm run backend:check',
  '# Open backend/examples/june-python.ipynb in Jupyter.\n# Read a cell, run it, change it, then run it again.\n\n# Example cell:\nmessages = ["Hello", "How are you?"]\nfor message in messages:\n    print(f"You: {message}")\n\n# Notebook state is practice state, not June’s memory.',
  'async with httpx.AsyncClient(trust_env=False) as client:\n    response = await client.get(\n        "http://127.0.0.1:8001/api/status"\n    )\n    print(response.json())\n\n# A stream produces pieces, not a finished string:\nasync for event in stream_chat(client, settings, mode, messages):\n    yield json.dumps(event) + "\\n"\n\n# June never detaches model work from its caller.',
  '@app.post("/api/chat")\nasync def chat(request: Request):\n    # Validate input before creating the stream.\n    return StreamingResponse(events(),\n                             media_type="application/x-ndjson")\n\n@app.websocket("/ws/chat")\nasync def socket_chat(socket: WebSocket):\n    await socket.accept()\n    # Receive requests; send delta/done/error events.\n    # A cancel message closes the active model stream.',
];

type Backend = { state: string; version?: string; websocketUrl?: string; message?: string };
type LabState = "idle" | "connecting" | "generating" | "complete" | "stopped" | "error";

export default function PhaseFour() {
  const [topic, setTopic] = useState(0);
  const [backend, setBackend] = useState<Backend | null>(null);
  const [prompt, setPrompt] = useState("Explain one useful thing about Python in two sentences.");
  const [reply, setReply] = useState("");
  const [phase, setPhase] = useState<LabState>("idle");
  const [notice, setNotice] = useState("");
  const [events, setEvents] = useState(0);
  const socket = useRef<WebSocket | null>(null);
  const request = useRef(0);
  const active = useRef(false);
  const deadline = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/backend", { signal: abort.signal, cache: "no-store" }).then(response => response.json()).then(data => {
      if (!abort.signal.aborted) setBackend(data);
    }).catch(() => { if (!abort.signal.aborted) setBackend({ state: "offline", message: "Restart June to connect her Python backend." }); });
    const hide = () => {
      if (document.hidden) {
        request.current++; active.current = false; clearTimeout(deadline.current); socket.current?.close(); socket.current = null;
        setPhase(previous => ["connecting", "generating"].includes(previous) ? "stopped" : previous);
      }
    };
    document.addEventListener("visibilitychange", hide);
    return () => { abort.abort(); request.current++; active.current = false; clearTimeout(deadline.current); socket.current?.close(); document.removeEventListener("visibilitychange", hide); };
  }, []);

  function stop() {
    // Closing the connection also cancels its server task. Never wait for a
    // delayed acknowledgement before making the controls usable again.
    request.current++; active.current = false; clearTimeout(deadline.current);
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: "cancel" }));
    socket.current?.close(); socket.current = null;
    setPhase("stopped"); setNotice("Stopped. You can start another request.");
  }

  function choose(index: number) { if (active.current) stop(); setTopic(index); }

  function run() {
    if (active.current || !prompt.trim() || !backend?.websocketUrl) return;
    active.current = true;
    const id = ++request.current;
    setReply(""); setEvents(0); setNotice(""); setPhase("connecting");
    let ws: WebSocket;
    try {
      const url = new URL(backend.websocketUrl);
      if (url.protocol !== "ws:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) throw new Error();
      ws = new WebSocket(url); socket.current = ws;
    } catch { active.current = false; setPhase("error"); setNotice("WebSockets are unavailable. Normal June chat still uses HTTP."); return; }
    function expire(message: string) {
      if (request.current !== id || !active.current) return;
      request.current++; active.current = false; ws.close();
      setPhase("error"); setNotice(message);
    }
    deadline.current = setTimeout(() => expire("The socket could not connect. Restart June, then refresh this page."), 10000);
    ws.onopen = () => {
      if (request.current !== id) { ws.close(); return; }
      clearTimeout(deadline.current);
      deadline.current = setTimeout(() => expire("The reply took too long. Try a shorter question."), 185000);
      setPhase("generating");
      ws.send(JSON.stringify({ mode: "local", messages: [{ role: "user", content: prompt.trim() }] }));
    };
    ws.onmessage = event => {
      if (request.current !== id) return;
      try {
        const data = JSON.parse(event.data);
        if (data.type === "delta" && typeof data.text === "string") { setReply(previous => previous + data.text); setEvents(previous => previous + 1); }
        else if (data.type === "done" || data.type === "error") {
          active.current = false; clearTimeout(deadline.current); setPhase(data.type === "done" ? "complete" : "error");
          setNotice(data.type === "done" ? "Complete · genuine local model reply" : data.message || "The local model could not finish.");
          ws.close();
        }
      } catch { active.current = false; clearTimeout(deadline.current); setPhase("error"); setNotice("The backend sent an invalid event. Try again."); ws.close(); }
    };
    ws.onerror = () => {
      if (request.current !== id || !active.current) return;
      active.current = false; clearTimeout(deadline.current); ws.close(); setPhase("error"); setNotice("Could not connect the learning socket. Restart June, or use normal chat.");
    };
    ws.onclose = () => {
      if (request.current !== id || !active.current) return;
      active.current = false; clearTimeout(deadline.current); setPhase("error"); setNotice("The connection ended before the reply completed. Try again.");
    };
  }

  const busy = phase === "connecting" || phase === "generating";
  return <div className="learn-page python-studio">
    <header className="masthead"><a className="wordmark" href="/">← june</a><span className="version">June v0.3.5 · Learning studio</span></header>
    <main>
      <div className="python-heading"><div><p className="eyebrow">Phase 4 · Python, the language of AI</p><h1>Behind the voice,<br /><em>a new foundation.</em></h1><p className="learn-intro">June’s interface stays familiar. Her model connection and local transcription now run in Python. Explore the code when you’re ready.</p></div><div className="python-seal"><span aria-hidden="true">py</span><small>LOCAL · PRIVATE · YOURS</small></div></div>
      <div className="python-flow" aria-label="June’s request flow">{["Your browser", "Next.js bridge", "Python backend", "Local AI engines"].map((name, i) => <div key={name}><span>0{i + 1}</span><strong>{name}</strong><small>{["Orb · recording · female voice", "Same-origin requests", "Validation · streaming · cleanup", "Qwen / Ollama · Whisper"][i]}</small></div>)}</div>
      <p className="backend-badge" role="status"><span className={`status-dot ${backend?.state === "ready" ? "ready" : "offline"}`} />{backend?.state === "ready" ? `Python backend ready · v${backend.version}` : backend?.message || "Checking Python backend…"}</p>
      <nav className="topic-nav" aria-label="Phase 4 topics">{topics.map((name, i) => <button key={name} aria-current={topic === i ? "step" : undefined} onClick={() => choose(i)}><span>4.{i + 1}</span>{name}</button>)}</nav>
      <section className="lesson-panel" aria-labelledby="python-topic"><p className="eyebrow">Explore · 4.{topic + 1}</p><h2 id="python-topic">{topics[topic]}</h2><p>{descriptions[topic]}</p><pre><code>{snippets[topic]}</code></pre>
        {topic === 2 && <p className="lesson-note">Your practice notebook is in <code>backend/examples/june-python.ipynb</code>. Install JupyterLab in the project environment only when you want to study it. June runs without Jupyter.</p>}
        {topic === 4 && <div className="python-lab"><div className="lab-heading"><h3>Watch the connection work.</h3><span>REAL LOCAL QWEN · NO VOICE IN THIS LAB</span></div><label htmlFor="lab-prompt">Ask the local model</label><textarea id="lab-prompt" rows={3} maxLength={2000} value={prompt} disabled={busy} onChange={event => setPrompt(event.target.value)} /><div className="audio-buttons"><button className="send-button" disabled={busy || !prompt.trim() || backend?.state !== "ready"} onClick={run}>Run WebSocket request <span aria-hidden="true">↗</span></button><button className="quiet-button" disabled={!busy} onClick={stop}>Stop request</button></div><div className="lab-readout"><span>{phase} · {events} text events</span><p className="message-text">{reply || "The model’s streamed words appear here."}</p><p role="status">{notice}</p></div><p className="lesson-note">This lab starts a fresh, temporary model conversation each time. It does not change your chat, voice preferences or learning checkboxes.</p></div>}
        <div className="lesson-footer"><span>{topic + 1} / 5 · Same order as your roadmap and workbook</span>{topic < 4 && <button className="quiet-button" onClick={() => choose(topic + 1)}>Next: {topics[topic + 1]} →</button>}</div>
      </section>
      <p className="learning-footer"><a href="/">← Back to June</a> · <a href="/learn/phase-3">Voice studio</a> · <a href="https://fastapi.tiangolo.com/tutorial/" target="_blank" rel="noreferrer">FastAPI tutorial ↗</a></p>
    </main>
  </div>;
}
