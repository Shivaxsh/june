"use client";

import { useEffect, useRef, useState } from 'react';

const topics = [
  { title: 'Voice frameworks', text: 'Pipecat connects small processors in an ordered pipeline. June uses a local detector processor followed by a turn manager. Accepted transcripts return to the same chat route used by typed messages.', code: 'Browser PCM → Pipecat detector → turn manager\n                         ↓\n            Whisper → transcript event\n                         ↓\n          /api/chat → Qwen → system voice', link: 'https://docs.pipecat.ai/pipecat/learn/pipeline' },
  { title: 'Wake phrases', text: 'Vosk listens locally for “Hey June” using a small English model and restricted vocabulary. It is an existing recognizer, not a newly trained wake-word model. Two seconds of recent audio preserve a question spoken immediately after the phrase. Accents and background sound affect accuracy.', code: 'recognizer = KaldiRecognizer(model, 16000,\n    \'["hey june", "[unk]"]\')\n# [unk] allows other sounds to remain unknown.\n# Detect both words; debounce repeated partial results.', link: 'https://alphacephei.com/vosk/install' },
  { title: 'Voice activity detection', text: 'Silero measures whether audio resembles speech. It does not understand the words. After at least half a second of voiced audio, a normal 1.5-second pause ends the question. Patient mode tolerates longer thinking pauses; each utterance is limited to 30 seconds.', code: 'if voiced:\n    voiced_seconds += packet_seconds\n    silence_seconds = 0\nelse:\n    silence_seconds += packet_seconds\n\nif voiced_seconds >= .5 and silence_seconds >= 1.5:\n    await transcribe_current_turn()', link: 'https://github.com/snakers4/silero-vad' },
  { title: 'Interruption', text: 'After activation, ordinary sustained speech can interrupt generation without the wake phrase. During playback, June briefly pauses and checks for continuing speech so speaker echo alone can resume the answer. A confirmed interruption advances the turn number before cancelling old work. Late results cannot resume the old reply. Keep speaking through the brief pause; a very short interjection or a noisy room may need another attempt. The wake phrase still works as an explicit interruption.', code: 'turn += 1\nabort_previous_request()\nstop_speech_queue()\n\n# Every delayed callback checks its owner:\nif callback_turn != current_turn:\n    return', link: 'https://developer.mozilla.org/en-US/docs/Web/API/AbortController' },
  { title: 'Turn-taking', text: 'Waiting → listening → transcribing → generating → speaking → follow-up. The 30-second follow-up window starts after both the reply and its spoken queue finish. A gap between streamed sentences is not the end of the turn. Expiry returns to waiting for the wake phrase.', code: 'if generation_complete and speech_queue_idle:\n    followup_deadline = now + 30\n\n# Stop, a hidden tab or a lost connection disarms June.\n# Reload never enables the microphone.', link: 'https://developer.mozilla.org/en-US/docs/Web/API/WebSocket' },
  { title: 'WebRTC', text: 'The working assistant sends PCM and control messages through one local WebSocket. WebRTC can negotiate peer connections, media tracks and data channels. This separate loopback lab sends a text packet between two peers inside this browser. It is not June’s audio transport and does not request a microphone.', code: 'const left = new RTCPeerConnection({ iceServers: [] });\nconst right = new RTCPeerConnection({ iceServers: [] });\nconst channel = left.createDataChannel("lesson");\n// Exchange an offer, answer and ICE candidates locally.\n// A real remote call also needs a signalling path.', link: 'https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection' },
  { title: 'Modular voice & speech-to-speech', text: 'June uses separate recognizer, language model and voice components: each can be inspected or replaced. A speech-to-speech model processes audio directly and may preserve timing and expression, but has different hardware and integration needs. June’s current mode remains entirely local; it is not a commercial real-time API.', code: 'June today:\nVosk + Silero → Whisper → Qwen → local female voice\n\nAlternative architecture:\naudio → speech-to-speech model → audio\n\nMeasure each stage before comparing responsiveness.', link: 'https://github.com/ggml-org/whisper.cpp' },
];

function Loopback() {
  const [phase, setPhase] = useState('Idle · no peer connection');
  const [active, setActive] = useState(false);
  const close = useRef<() => void>(() => {});
  useEffect(() => {
    const stop = () => { close.current(); setActive(false); setPhase('Stopped · connections released'); };
    const hide = () => { if (document.hidden) stop(); };
    document.addEventListener('visibilitychange', hide); window.addEventListener('pagehide', stop);
    return () => { close.current(); document.removeEventListener('visibilitychange', hide); window.removeEventListener('pagehide', stop); };
  }, []);
  async function run() {
    close.current();
    if (!window.RTCPeerConnection) { setPhase('WebRTC is unavailable in this browser. The working assistant uses WebSockets.'); return; }
    setActive(true); setPhase('Negotiating two local peers…');
    const peers: RTCPeerConnection[] = [];
    let alive = true, timer: ReturnType<typeof setTimeout>;
    close.current = () => { alive = false; clearTimeout(timer); peers.forEach(peer => { peer.onicecandidate = peer.ondatachannel = null; peer.close(); }); };
    try {
      const left = new RTCPeerConnection({ iceServers: [] }), right = new RTCPeerConnection({ iceServers: [] }); peers.push(left, right);
      const pending: RTCIceCandidate[][] = [[], []];
      const forward = async (target: RTCPeerConnection, candidate: RTCIceCandidate | null, index: number) => {
        if (!candidate || !alive) return;
        if (!target.remoteDescription) pending[index].push(candidate);
        else await target.addIceCandidate(candidate);
      };
      const failed = () => { if (alive) { close.current(); setActive(false); setPhase('Loopback could not connect. Browser policy may block local peers; June’s WebSocket mode is separate.'); } };
      left.onicecandidate = event => { void forward(right, event.candidate, 1).catch(failed); };
      right.onicecandidate = event => { void forward(left, event.candidate, 0).catch(failed); };
      const channel = left.createDataChannel('june-lesson');
      right.ondatachannel = event => { event.channel.onmessage = message => { if (alive) { setPhase(`Received through WebRTC: ${String(message.data)}`); clearTimeout(timer); } }; };
      channel.onopen = () => { if (alive) channel.send('Hello from June’s loopback peer.'); };
      channel.onerror = failed;
      timer = setTimeout(failed, 12000);
      await left.setLocalDescription(await left.createOffer()); if (!alive) return;
      await right.setRemoteDescription(left.localDescription!); if (!alive) return;
      for (const candidate of pending[1].splice(0)) await right.addIceCandidate(candidate);
      await right.setLocalDescription(await right.createAnswer()); if (!alive) return;
      await left.setRemoteDescription(right.localDescription!); if (!alive) return;
      for (const candidate of pending[0].splice(0)) await left.addIceCandidate(candidate);
    } catch { if (alive) { close.current(); setActive(false); setPhase('WebRTC could not start here. No microphone was requested.'); } }
  }
  return <div className="python-lab"><div className="lab-heading"><h3>Two peers. One browser.</h3><span>WEBRTC DATA-CHANNEL DEMO</span></div><p>No microphone, external signalling server, STUN or TURN service. This local data-channel demonstration is separate from the voice assistant.</p><div className="talk-controls"><button className="quiet-button" disabled={active} onClick={() => void run()}>Run WebRTC loopback</button><button className="quiet-button" disabled={!active} onClick={() => { close.current(); setActive(false); setPhase('Stopped · connections released'); }}>Stop loopback</button></div><p role="status">{phase}</p></div>;
}

export default function PhaseFive() {
  const [topic, setTopic] = useState(0);
  const [status, setStatus] = useState('Checking local voice engines…');
  useEffect(() => {
    const abort = new AbortController();
    fetch('/api/voice/status', { signal: abort.signal, cache: 'no-store' }).then(response => response.json()).then(data => { if (!abort.signal.aborted) setStatus(typeof data.message === 'string' ? data.message : 'Voice status unavailable.'); }).catch(() => { if (!abort.signal.aborted) setStatus('Restart June to connect her local voice engines.'); });
    return () => abort.abort();
  }, []);
  const lesson = topics[topic];
  return <div className="learn-page python-studio"><header className="masthead"><a className="wordmark" href="/">← june</a><span className="version">Learning studio · Phase 5</span></header><main><p className="eyebrow">June v0.4 · A conversation in motion</p><h1>Make room<br />for <em>the next word.</em></h1><p className="learn-intro">A voice assistant is a series of small decisions: when to listen, when to wait, when to answer, and when to stop. Explore the seven parts behind June’s hands-free mode.</p><p className="backend-badge" role="status">● {status}</p><div className="python-flow">{['Wake locally', 'Find a turn', 'Think & speak', 'Keep listening'].map((name, index) => <div key={name}><span>0{index + 1}</span><strong>{name}</strong><small>{['Vosk hears the chosen phrase.', 'Silero finds a pause; Whisper transcribes.', 'Qwen replies; your system voice speaks.', '30 seconds for a follow-up.'][index]}</small></div>)}</div><nav className="topic-nav" aria-label="Phase 5 topics">{topics.map((item, index) => <button key={item.title} aria-current={topic === index ? 'step' : undefined} onClick={() => setTopic(index)}><span>5.{index + 1}</span>{item.title}</button>)}</nav><section className="lesson-panel" aria-labelledby="lesson-title"><p className="eyebrow">5.{topic + 1} · Follow the workbook</p><h2 id="lesson-title">{lesson.title}</h2><p className="lesson-intro">{lesson.text}</p><pre><code>{lesson.code}</code></pre>{topic === 5 && <Loopback />}<p><a className="learn-link" href={lesson.link} target="_blank" rel="noreferrer">Read the official documentation ↗</a></p><div className="lesson-footer"><span>Inspect: backend/june/realtime_*.py · lib/voice/realtime-*.ts</span><button className="quiet-button" onClick={() => setTopic((topic + 1) % topics.length)}>Next topic →</button></div></section><p className="learning-footer">Try the working mode in <a href="/">June’s conversation page</a>. Microphone access starts only when you enable it. Human conversation verification is required before completing Phase 5.</p></main></div>;
}
