"use client";
import { useEffect, useRef, useState } from 'react';
import { fetchVoiceConfig, HandsFreeController, type HandsFreeState, type VoiceConfig, type AudioSourceOptions } from '@/lib/voice/realtime-client';
import { RealtimeCapture } from '@/lib/voice/realtime-capture';

export function useHandsFree(callbacks: { wake(turn: number): void; transcript(text: string, turn: number): void; cancel(): void; pause(): boolean | Promise<boolean | null>; resume(): void; audio(): AudioSourceOptions; status: VoiceConfig; refresh(): Promise<void> }) {
  const latest = useRef(callbacks); latest.current = callbacks;
  const controller = useRef<HandsFreeController | null>(null);
  const [state, setState] = useState<HandsFreeState>({ phase: 'off', error: '', turn: 0, vad: 0, transcriptionMs: 0 });
  const [pause, setPause] = useState('short');
  const level = useRef(0);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    controller.current = new HandsFreeController(() => new RealtimeCapture(level), url => new WebSocket(url), fetchVoiceConfig,
      value => { if (mounted.current) { if (value.audioSource === 'native') level.current = value.level ?? 0; else if (value.phase === 'off') level.current = 0; setState(value); } }, {
        wake: turn => latest.current.wake(turn), transcript: (text, turn) => latest.current.transcript(text, turn), cancel: () => latest.current.cancel(),
        pause: () => latest.current.pause(), resume: () => latest.current.resume(),
      });
    const stop = () => controller.current?.stop();
    const hide = () => { if (document.hidden) stop(); };
    window.addEventListener('pagehide', stop); document.addEventListener('visibilitychange', hide);
    return () => {
      mounted.current = false; controller.current?.stop(); controller.current = null;
      window.removeEventListener('pagehide', stop); document.removeEventListener('visibilitychange', hide);
    };
  }, []);
  return { audioSource: callbacks.audio().audioSource, sessionId: () => controller.current?.sessionId || '', state, status: callbacks.status, pause, setPause, level, refresh: callbacks.refresh, active: state.phase !== 'off',
    start: () => { void controller.current?.start(pause, latest.current.audio()); }, stop: (message = '') => controller.current?.stop(message),
    activity: (phase: 'generating' | 'speaking' | 'complete' | 'failed', text = '') => controller.current?.activity(phase, text),
  };
}
export type HandsFreeControls = ReturnType<typeof useHandsFree>;
