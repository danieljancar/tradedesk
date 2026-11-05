import { useCallback, useEffect, useRef, useState } from "react";

export type Run = { id: string; started_at: string; finished_at: string | null; status: string; summary: string | null };
export type DeskEvent = { id: number; run_id: string; ts: string; actor: string; kind: string; title: string; body: string | null; html: string; refs: string[] };
export type Plan = Record<string, any> & { id: string; venue?: string; asset: string; side: string; status: string };
export type Position = Record<string, any> & { id: string; venue?: string; asset: string; side: string };
export type DeskState = {
  mode: string; market: string; quote: string; auto_execute?: boolean; watchlist?: string[];
  telegram?: { enabled: boolean; configured: boolean };
  peer?: string | null; venues?: string[];
  limits?: { risk_per_trade_pct: number; max_open_positions: number; daily_loss_limit_pct: number; max_leverage: number } & Record<string, number>;
  equity: { ts: string; value: number }[];
  positions: Position[]; plans: Plan[]; closed: Position[];
};
export type Candle = { time: number; open: number; high: number; low: number; close: number; volume: number };

export async function api<T>(path: string, method = "GET"): Promise<T> {
  const res = await fetch(path, { method, headers: method === "GET" ? {} : { "X-Desk": "1" } });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

export function useInterval(fn: () => void, ms: number) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    const t = setInterval(() => ref.current(), ms);
    return () => clearInterval(t);
  }, [ms]);
}

/** Runs, the selected run's events (incremental) and facts, and the account state. */
export function useDesk() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<DeskEvent[]>([]);
  const [fresh, setFresh] = useState<DeskEvent[]>([]);
  const [facts, setFacts] = useState<any>(null);
  const [state, setState] = useState<DeskState | null>(null);
  const last = useRef(0);
  const current = useRef<string | null>(null);

  const loadState = useCallback(() => api<DeskState>("/api/state").then(setState).catch(console.error), []);
  const loadFacts = useCallback((id: string) => api<any>(`/api/runs/${encodeURIComponent(id)}/facts`).then(setFacts).catch(() => setFacts(null)), []);

  const poll = useCallback(async (live: boolean) => {
    const id = current.current;
    if (!id) return;
    const got = await api<DeskEvent[]>(`/api/runs/${encodeURIComponent(id)}/events?after=${last.current}`);
    if (current.current !== id || !got.length) return;
    last.current = got.at(-1)!.id;
    setEvents((prev) => [...prev, ...got]);
    if (live) setFresh(got);
    if (live && got.some((e) => e.actor === "prices" && e.kind !== "start")) loadFacts(id);
  }, [loadFacts]);

  const select = useCallback(async (id: string) => {
    current.current = id;
    last.current = 0;
    setRunId(id);
    setEvents([]);
    setFresh([]);
    setFacts(null);
    await Promise.all([poll(false), loadFacts(id)]);
  }, [poll, loadFacts]);

  const tick = useCallback(async () => {
    try {
      const rs = await api<Run[]>("/api/runs");
      setRuns(rs);
      // always follow the newest run, so a run that starts tonight shows up live
      if (rs[0] && current.current !== rs[0].id) await select(rs[0].id);
      else await poll(true);
    } catch (e) {
      console.error(e);
    }
  }, [poll, select]);

  useEffect(() => { tick(); loadState(); }, [tick, loadState]);
  useInterval(tick, 2500);
  useInterval(loadState, 15000);

  return { runs, runId, select, events, fresh, facts, state, refresh: () => Promise.all([loadState(), poll(true)]) };
}
