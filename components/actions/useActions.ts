"use client";
import { useCallback, useEffect, useState } from "react";
import { getActions, mergeAction, mergeActions, type ActionRecord, type ActionState } from "@/lib/actions";

/** The server's list of recent actions. One shared server clock reference keeps every countdown honest. */
export function useActions() {
  const [state, setState] = useState<ActionState | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try {
      const next = await getActions(), at = Date.now();
      // Merge rather than replace: a slow GET must not undo an outcome a faster reply already showed.
      setState(previous => ({ ...next, actions: mergeActions(previous?.actions ?? [], next.actions) }));
      setReceivedAt(at); setError("");
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Hands is unavailable."); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const upsert = useCallback((record: ActionRecord, serverNow: number) => {
    setState(previous => {
      const known = previous?.actions.find(a => a.id === record.id);
      // Keep the last observed app snapshot (and its age); only a refresh replaces it.
      return { ...previous, serverNow, available: previous?.available ?? true, openVSCodeWithoutApproval: previous?.openVSCodeWithoutApproval ?? false, actions: [mergeAction(known, record), ...(previous?.actions ?? []).filter(a => a.id !== record.id)] };
    });
    setReceivedAt(Date.now());
  }, []);
  /** A full state from the server (for example after changing the review setting), merged monotonically. */
  const replace = useCallback((next: ActionState) => {
    setState(previous => ({ ...next, actions: mergeActions(previous?.actions ?? [], next.actions) }));
    setReceivedAt(Date.now());
  }, []);
  return { state, receivedAt, error, refresh, upsert, replace };
}
export type Actions = ReturnType<typeof useActions>;
