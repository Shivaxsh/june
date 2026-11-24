"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getTransaction, type Transaction } from "@/lib/transactions";
import type { Plan } from "@/lib/integrations";

/** Transactions shown in chat (from June's replies), kept fresh: when a transaction's plan finishes, its receipt is
 * re-read once (read-only: never a second commit). Older replies never overwrite newer ones. */
export function useTransactions(plans: Plan[]) {
  const [items, setItems] = useState<Record<string, Transaction>>({});
  const seq = useRef(0), latest = useRef<Record<string, number>>({});
  const handled = useRef(new Set<string>());
  const upsert = useCallback((t: Transaction) => {
    latest.current[t.id] = ++seq.current;
    setItems(now => ({ ...now, [t.id]: t }));
  }, []);
  const refresh = useCallback(async (id: string) => {
    const token = latest.current[id] = ++seq.current;
    try {
      const { transaction } = await getTransaction(id);
      if (latest.current[id] === token) setItems(now => ({ ...now, [id]: transaction }));
    } catch { /* the card keeps its last known state */ }
  }, []);
  useEffect(() => {
    for (const t of Object.values(items)) {
      const plan = t.planId ? plans.find(p => p.id === t.planId) : undefined;
      if (!plan || ["proposed", "approved", "running"].includes(plan.status)) continue;
      const mark = `${t.id}:${plan.id}:${plan.status}`;
      if (handled.current.has(mark)) continue;
      handled.current.add(mark);
      void refresh(t.id);
    }
  }, [items, plans, refresh]);
  return { items, upsert, refresh };
}
