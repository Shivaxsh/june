"use client";
import { useEffect, useRef, useState } from "react";
const examples = [
  'context.beginPath();\ncontext.arc(200, 200, 64, 0, Math.PI * 2);\ncontext.fillStyle = "#8ee9d0";\ncontext.fill();',
  'const dots = [{ x: 120, y: 180 }, { x: 220, y: 100 }, { x: 285, y: 230 }];\nfor (const dot of dots) {\n  context.beginPath();\n  context.arc(dot.x, dot.y, 5, 0, Math.PI * 2);\n  context.fill();\n}',
  'context.beginPath();\ncontext.moveTo(dots[0].x, dots[0].y);\ncontext.lineTo(dots[1].x, dots[1].y);\ncontext.stroke();',
  'function frame(time) {\n  context.clearRect(0, 0, 400, 400);\n  // Move, draw the dots, then connect nearby neighbours.\n  drawNetwork(time / 1000);\n  requestAnimationFrame(frame);\n}\nrequestAnimationFrame(frame);',
];
export default function CanvasLesson() {
  const [step, setStep] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d"); if (!ctx) return;
    const motion = matchMedia("(prefers-reduced-motion: reduce)"); let frame = 0;
    const draw = (time: number) => {
      ctx.clearRect(0, 0, 400, 400); ctx.fillStyle = "#8ee9d0"; ctx.strokeStyle = "#8ee9d060";
      if (step === 0) { ctx.beginPath(); ctx.arc(200, 200, 64, 0, Math.PI * 2); ctx.fill(); }
      else {
        const points = Array.from({ length: step === 3 ? 24 : 6 }, (_, i) => {
          const angle = i * 2.399 + (step === 3 && !motion.matches ? time / 9000 : 0);
          return { x: 200 + Math.cos(angle) * (75 + i * 2), y: 200 + Math.sin(angle) * (75 + i * 2) };
        });
        for (const a of points) {
          ctx.beginPath(); ctx.arc(a.x, a.y, 4, 0, Math.PI * 2); ctx.fill();
          if (step >= 2) for (const b of points) if (Math.hypot(a.x - b.x, a.y - b.y) < 110) {
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
      }
      if (step === 3 && !motion.matches && !document.hidden) frame = requestAnimationFrame(draw);
    };
    const refresh = () => { cancelAnimationFrame(frame); if (!document.hidden) frame = requestAnimationFrame(draw); };
    motion.addEventListener("change", refresh); document.addEventListener("visibilitychange", refresh); refresh();
    return () => { cancelAnimationFrame(frame); motion.removeEventListener("change", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [step]);
  return <><div className="lesson-steps">{["One circle", "Dot array", "Connections", "Animation"].map((name, i) => <button key={name} className="quiet-button" aria-pressed={step === i} onClick={() => setStep(i)}>{name}</button>)}</div><div className="lesson-example"><canvas ref={canvas} width="400" height="400" role="img" aria-label={`Canvas exercise: ${["one circle", "dot array", "connections", "animation"][step]}`} /><pre><code>{examples[step]}</code></pre></div><p className="lesson-note">The examples show the key idea. The complete renderer also handles resizing, timing, reduced motion and cleanup.</p></>;
}
