"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AudioController, type AudioState } from "@/lib/orb/audio-controller";

export function useAudio() {
  const engine = useRef<AudioController | null>(null);
  const level = useRef(0);
  const [state, setState] = useState<AudioState>({ phase: "idle", error: "" });
  useEffect(() => {
    const controller = new AudioController(setState, level);
    engine.current = controller;
    const leave = () => controller.stop();
    const hide = () => { if (document.hidden) controller.stop(); };
    window.addEventListener("pagehide", leave);
    document.addEventListener("visibilitychange", hide);
    return () => {
      controller.dispose(); engine.current = null;
      window.removeEventListener("pagehide", leave);
      document.removeEventListener("visibilitychange", hide);
    };
  }, []);
  const stop = useCallback(() => engine.current?.stop(), []);
  return { ...state, level, stop, play: (file?: File) => engine.current?.play(file),
    pause: () => engine.current?.pause(), microphone: () => engine.current?.microphone() };
}
export type AudioControls = ReturnType<typeof useAudio>;
