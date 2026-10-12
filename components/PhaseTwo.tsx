"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import CanvasLesson from "./orb/CanvasLesson";
import Orb from "./orb/Orb";
import OrbControls from "./orb/OrbControls";
import AudioPanel from "./orb/AudioPanel";
import { useAudio } from "./orb/useAudio";
import { resolveOrb, type Preview } from "@/lib/orb/state";
// WebGL and Three.js load only when a learning demonstration needs them.
const GraphicsDemo = dynamic(() => import("./orb/GraphicsDemo"), { ssr: false, loading: () => <p>Opening the graphics example…</p> });
const topics = ["Canvas 2D", "Three.js", "Web Audio API", "Shaders · GLSL", "Mood states", "React Three Fiber"];
const introductions = [
  "A canvas is a drawing surface. JavaScript supplies the coordinates, colours and shapes. Start with one circle, then build up the network.",
  "A scene holds your objects. A camera chooses the view. A renderer draws that view. These dots use real 3D coordinates; the main June orb uses lighter Canvas drawing.",
  "An analyser reads the sound wave many times a second. Its measured amplitude changes the orb and meter. The movement follows the signal, rather than a timer pretending to hear.",
  "A shader runs on the graphics processor. Here the fragment shader gives each pixel a colour and opacity based on its distance from the centre. Time gently moves the rings.",
  "Mood is a small piece of state. The chat uses real request and audio activity; these buttons let you inspect the four appearances deliberately.",
  "React Three Fiber is an optional React renderer for Three.js. Learn the scene, camera and renderer first. June v0.2 does not need this extra dependency.",
];
export default function PhaseTwo() {
  const [topic, setTopic] = useState(0);
  const [fallback, setFallback] = useState(false);
  const [preview, setPreview] = useState<Preview>("auto");
  const [still, setStill] = useState(false);
  const audio = useAudio();
  const orb = resolveOrb(false, false, preview, audio.phase);
  function choose(index: number) { audio.stop(); setPreview("auto"); setFallback(false); setTopic(index); }
  return <div className="learn-page"><header className="masthead"><a className="wordmark" href="/">← june</a><span className="version">June v0.2 · Learning studio</span></header>
    <main><p className="eyebrow">Phase 2 · A face, built one idea at a time</p><h1>Meet the little things<br />that make her <em>move.</em></h1><p className="learn-intro">Six stops, in the same order as your workbook. Open one, explore it, then look at the small piece of code behind it.</p>
    <nav className="topic-nav" aria-label="Phase 2 topics">{topics.map((name, i) => <button key={name} aria-current={topic === i ? "step" : undefined} onClick={() => choose(i)}><span>2.{i + 1}</span>{name}{i === 5 && <small>Optional</small>}</button>)}</nav>
    <section className="lesson-panel" aria-labelledby="topic-heading"><p className="eyebrow">Explore · 2.{topic + 1}</p><h2 id="topic-heading">{topics[topic]}</h2><p className="lesson-intro">{introductions[topic]}</p>
      {topic === 0 && <CanvasLesson />}
      {(topic === 1 || topic === 3) && <><label className="motion-option"><input type="checkbox" checked={fallback} onChange={event => setFallback(event.target.checked)} /> Show ordinary rendering fallback</label><GraphicsDemo key={`${topic}-${fallback}`} shader={topic === 3} fallback={fallback} /><pre><code>{topic === 1 ? 'const scene = new THREE.Scene();\nconst camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);\ncamera.position.z = 4.2;\nscene.add(particles);\nrenderer.render(scene, camera);' : 'float distanceFromCentre = length(uvPoint - 0.5);\nfloat glow = exp(-distanceFromCentre * 7.0);\nfloat rings = 0.5 + 0.5 * sin(distanceFromCentre * 40.0 - time * 1.5);\ngl_FragColor = vec4(colour, glow * (0.75 + rings * 0.25));'}</code></pre><p className="lesson-note">The example releases its geometry, material and renderer when you switch topics.</p></>}
      {(topic === 2 || topic === 4) && <><div className="lesson-orb"><Orb mood={orb.mood} label={orb.label} level={audio.level} still={still} /><OrbControls preview={preview} onPreview={setPreview} still={still} onStill={setStill} /></div>{topic === 2 && <><AudioPanel audio={audio} onActivate={() => setPreview("auto")} /><pre><code>{'analyser.getFloatTimeDomainData(samples);\nconst rms = Math.sqrt(samples.reduce((sum, x) => sum + x * x, 0) / samples.length);\nconst level = Math.min(1, rms * 5);\n// Smooth the level, then let the Canvas renderer read it.'}</code></pre></>}{topic === 4 && <><dl className="state-explainer"><dt>Idle</dt><dd>Slow rotation and a teal glow.</dd><dt>Listening</dt><dd>A blue accent and an upper arc. A real microphone reads sound only.</dd><dt>Thinking</dt><dd>Faster signals and a violet core while a reply is generated.</dd><dt>Speaking</dt><dd>A warm glow and lower arc. Phase 2 uses audio playback or a labelled preview.</dd></dl><p className="lesson-note">In chat, generation has priority. Sending a message exits preview; Stop and New chat restore the correct activity state.</p></>}</>}
      {topic === 5 && <><p>You can later express a scene using React components such as <code>Canvas</code>, <code>mesh</code> and <code>points</code>. Props describe the scene; animation callbacks update it.</p><p>For this phase, the working Canvas orb and the ordinary Three.js example already demonstrate the required ideas.</p><a className="learn-link" href="https://r3f.docs.pmnd.rs/getting-started/introduction" target="_blank" rel="noreferrer">Read the optional React Three Fiber introduction ↗</a></>}
      <div className="lesson-footer"><span>{topic + 1} / 6 · Explore at your own pace</span>{topic < 5 && <button className="quiet-button" onClick={() => choose(topic + 1)}>Next: {topics[topic + 1]} →</button>}</div>
    </section><p className="learning-footer"><a href="/">← Back to your conversation</a> · Exploring a demo does not mark a learning topic complete.</p></main></div>;
}
