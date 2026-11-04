import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { api, useDesk, useInterval } from "@/lib/api";

export type Note = { id: number; ts: string; kind: string; asset: string | null; price: number | null; text: string };
export type Headline = { title: string; link: string; source: string; category: string; ts: number };
export type UniverseAsset = {
  asset: string; asset_class: "crypto" | "gold"; source: "watchlist" | "always" | "gold" | "core" | "scan";
  score: number | null; price: number | null; change_24h: number | null; change_7d: number | null; rel_btc_7d: number | null;
  vol_surge: number | null; atr_pct: number | null; quote_volume: number | null; reason: string | null;
};

type Ctx = ReturnType<typeof useDesk> & {
  notes: Note[];
  addNote: (n: { kind?: string; text: string; asset?: string | null; price?: number | null }) => Promise<void>;
  dropNote: (id: number) => Promise<void>;
  news: Headline[];
  macro: any;
  runNow: () => Promise<void>;
  act: (path: string, method?: string, ok?: string, body?: unknown) => Promise<boolean>;
  watch: string[];
  universe: UniverseAsset[];
};

const DeskCtx = createContext<Ctx | null>(null);

export async function send(path: string, method = "POST", body?: unknown) {
  const res = await fetch(path, {
    method,
    headers: { "X-Desk": "1", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

export function DeskProvider({ children }: { children: ReactNode }) {
  const desk = useDesk();
  const [notes, setNotes] = useState<Note[]>([]);
  const [news, setNews] = useState<Headline[]>([]);
  const [macro, setMacro] = useState<any>(null);
  const [universe, setUniverse] = useState<UniverseAsset[]>([]);
  const runId = desk.runId;
  const scanned = desk.events.some((e) => e.actor === "scanner" && e.kind === "output");

  const loadNotes = useCallback(() => api<Note[]>("/api/notes").then(setNotes).catch(() => {}), []);
  const loadNews = useCallback(() => api<Headline[]>("/api/news").then(setNews).catch(() => {}), []);
  const loadMacro = useCallback(() => api<any>("/api/macro").then(setMacro).catch(() => {}), []);
  useEffect(() => { loadNotes(); loadNews(); loadMacro(); }, [loadNotes, loadNews, loadMacro]);
  useInterval(loadNews, 120_000);
  useInterval(loadMacro, 900_000);
  useEffect(() => {
    if (!runId) return;
    api<UniverseAsset[]>(`/api/universe?run_id=${encodeURIComponent(runId)}`).then(setUniverse).catch(() => setUniverse([]));
  }, [runId, scanned]);

  const act = useCallback(async (path: string, method = "POST", ok?: string, body?: unknown) => {
    try {
      await send(path, method, body);
      if (ok) toast.success(ok);
      await desk.refresh();
      return true;
    } catch (e: any) {
      toast.error(e.message);
      return false;
    }
  }, [desk]);

  const addNote = useCallback(async (n: { kind?: string; text: string; asset?: string | null; price?: number | null }) => {
    if (await act("/api/notes", "POST", n.kind === "level" ? "Level saved, the desk will see it" : "Note saved, the desk reads it next run", { kind: "note", ...n })) loadNotes();
  }, [act, loadNotes]);
  const dropNote = useCallback(async (id: number) => { if (await act(`/api/notes/${id}`, "DELETE")) loadNotes(); }, [act, loadNotes]);
  const runNow = useCallback(async () => { await act("/api/run", "POST", "Desk run started. Watch it on the Desk page."); }, [act]);

  const watch = universe.length
    ? [...new Set(universe.map((u) => u.asset))]
    : [...new Set(["BTC", "ETH", ...(desk.state?.watchlist ?? [])])];

  return <DeskCtx.Provider value={{ ...desk, notes, addNote, dropNote, news, macro, runNow, act, watch, universe }}>{children}</DeskCtx.Provider>;
}

export function useDeskCtx() {
  const c = useContext(DeskCtx);
  if (!c) throw new Error("DeskProvider missing");
  return c;
}
