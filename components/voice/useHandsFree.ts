"use client";
import { useEffect, useRef, useState } from 'react';
import { HandsFreeController, type HandsFreeState } from '@/lib/voice/realtime-client';
import { RealtimeCapture } from '@/lib/voice/realtime-capture';

export function useHandsFree(callbacks: { wake(turn: number): void; transcript(text: string, turn: number): void; cancel(): void; pause(): boolean | Promise<boolean | null>; resume(): void }) {
  const latest = useRef(callbacks); latest.current = callbacks;
  const controller = useRef<HandsFreeController | null>(null);
  const [state, setState] = useState<HandsFreeState>({ phase: 'off', error: '', turn: 0, vad: 0, transcriptionMs: 0 });
  const [status, setStatus] = useState({ state: 'checking', message: 'Checking local hands-free…' });
  const [pause, setPause] = useState('normal');
  const level = useRef(0);
  const mounted = useRef(false);
  async function config(signal: AbortSignal) {
    const response = await fetch('/api/voice/status', { cache: 'no-store', signal });
    const data = await response.json();
    if (!response.ok || typeof data?.state !== 'string' || typeof data?.message !== 'string') throw Error('Hands-free status is unavailable. Restart June, then refresh.');
    return data;
  }
  async function refresh() {
    try {
      const value = await config(AbortSignal.timeout(12000));
      if (mounted.current) setStatus(value);
    } catch { if (mounted.current) setStatus({ state: 'error', message: 'Hands-free status is unavailable. Restart June, then refresh.' }); }
  }
  useEffect(() => {
    mounted.current = true;
    controller.current = new HandsFreeController(() => new RealtimeCapture(level), url => new WebSocket(url), config,
      value => { if (mounted.current) setState(value); }, {
        wake: turn => latest.current.wake(turn), transcript: (text, turn) => latest.current.transcript(text, turn), cancel: () => latest.current.cancel(),
        pause: () => latest.current.pause(), resume: () => latest.current.resume(),
      });
    void refresh();
    const stop = () => controller.current?.stop();
    const hide = () => { if (document.hidden) stop(); };
    window.addEventListener('pagehide', stop); document.addEventListener('visibilitychange', hide);
    return () => {
      mounted.current = false; controller.current?.stop(); controller.current = null;
      window.removeEventListener('pagehide', stop); document.removeEventListener('visibilitychange', hide);
    };
  }, []);
  return { state, status, pause, setPause, level, refresh, active: state.phase !== 'off',
    start: () => { void controller.current?.start(pause); }, stop: (message = '') => controller.current?.stop(message),
    activity: (phase: 'generating' | 'speaking' | 'complete' | 'failed', text = '') => controller.current?.activity(phase, text),
  };
}
export type HandsFreeControls = ReturnType<typeof useHandsFree>;
