"use client";
import {useCallback, useEffect, useRef, useState} from "react";
import {libraryRequest, type LibraryState} from "@/lib/memory-types";

export function useLibrary(onReset: () => void) {
  const [data,setData] = useState<LibraryState | null>(null);
  const [error,setError] = useState("");
  const [temporary,setTemporary] = useState(false);
  const reset = useRef(onReset); reset.current = onReset;
  const revision = useRef<number | null>(null);
  const channel = useRef<BroadcastChannel | null>(null);
  const mounted = useRef(true);
  const refreshing = useRef(false);
  const refresh = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      const next = await libraryRequest<LibraryState>("state");
      if (!mounted.current) return;
      if (!Number.isInteger(next.revision) || !Array.isArray(next.memories) || !next.profile) throw new Error("June returned invalid storage information.");
      if (revision.current !== null && revision.current !== next.revision) reset.current();
      revision.current = next.revision;
      setData(next);setError("");
    } catch (e) {if (mounted.current) setError(e instanceof Error ? e.message : "Private storage failed.");}
    finally {refreshing.current = false;}
  },[]);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    const timer = setInterval(() => {if (!document.hidden) void refresh();},1500);
    const focus = () => void refresh();
    window.addEventListener("focus",focus);
    if (typeof BroadcastChannel !== "undefined") {
      channel.current = new BroadcastChannel("june-private-library");
      channel.current.onmessage = () => {reset.current(); void refresh();};
    }
    return () => {mounted.current=false;clearInterval(timer);window.removeEventListener("focus",focus);channel.current?.close();};
  },[refresh]);
  async function mutate<T>(path:string,method:string,value?:unknown) {
    // Stop local speech immediately. Server cancellation and revision checks protect other tabs.
    reset.current();
    const result = await libraryRequest<T>(path,method,value);
    channel.current?.postMessage({changed:true});
    await refresh();
    return result;
  }
  return {data,error,temporary,refresh,mutate,setTemporary:(value:boolean) => {reset.current();setTemporary(value);}};
}
export type Library = ReturnType<typeof useLibrary>;
