import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { BookOpen, ChevronRight, Moon, RefreshCw, Sun } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Floor, said } from "@/components/floor";
import { PriceChart } from "@/components/price-chart";
import { Prose } from "@/components/prose";
import { Avatar } from "@/components/panels";
import { OverviewView } from "@/components/overview";
import { CAST } from "@/lib/cast";
import { GLOSSARY, pc, planStory, px, readAsset, readMood } from "@/lib/learn";
import { api, useInterval, type Candle, type DeskEvent, type DeskState, type Plan, type Run } from "@/lib/api";
import { cn } from "@/lib/utils";

const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const money = (n: number) => `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(2)}`;
const tone = (n: number | null | undefined) => (n == null ? "" : n >= 0 ? "text-up" : "text-down");
export const runLabel = (id: string) => {
  const d = new Date(id.replace(/T(\d\d)(\d\d)$/, "T$1:$2:00Z"));
  return Number.isNaN(+d) ? id : d.toLocaleString([], { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
};

// ---------- small building blocks ----------
function Panel({ title, right, children, className, bodyClass }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={cn("flex min-h-0 flex-col bg-panel", className)}>
      {title != null && (
        <header className="flex h-9 shrink-0 items-center gap-2 border-b border-line px-3">
          <h2 className="text-[11px] font-semibold tracking-[0.08em] text-dim uppercase">{title}</h2>
          <div className="ml-auto flex items-center gap-1">{right}</div>
        </header>
      )}
      <div className={cn("min-h-0 flex-1", bodyClass)}>{children}</div>
    </section>
  );
}

function Seg<T extends string>({ value, options, onChange, size = "sm" }: { value: T; options: { v: T; label: ReactNode }[]; onChange: (v: T) => void; size?: "sm" | "md" }) {
  return (
    <div className="flex items-center gap-0.5 rounded-md bg-sunk p-0.5" role="tablist">
      {options.map((o) => (
        <button key={o.v} type="button" role="tab" aria-selected={value === o.v} onClick={() => onChange(o.v)}
          className={cn("rounded-[5px] px-2 font-medium tabular-nums transition-colors", size === "sm" ? "h-6 text-xs" : "h-7 text-[13px]",
            value === o.v ? "bg-raised text-fg shadow-sm" : "text-dim hover:text-fg")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Explain({ term, text, children }: { term?: string; text?: string; children: ReactNode }) {
  const g = term ? GLOSSARY[term] : null;
  return (
    <HoverCard openDelay={120} closeDelay={60}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent side="left" align="start" className="w-72 space-y-1.5 p-3 text-[13px] leading-snug">
        {g && <p className="font-semibold">{g.term}</p>}
        {text && <p>{text}</p>}
        {g && <p className="text-dim">{g.short}</p>}
      </HoverCardContent>
    </HoverCard>
  );
}

// ---------- live tickers ----------
type Tick = { price: number; ch: number; spark: number[] };
export function useTickers(assets: string[]) {
  const [ticks, setTicks] = useState<Record<string, Tick>>({});
  const load = () => assets.forEach((a) =>
    api<Candle[]>(`/api/candles/${a}?tf=1h&limit=48`).catch(() => api<Candle[]>(`/api/candles/${a}?tf=4h&limit=24`))
      .then((c) => {
        if (!c.length) return;
        const last = c.at(-1)!.close, dayAgo = c[Math.max(0, c.length - 25)].close;
        setTicks((t) => ({ ...t, [a]: { price: last, ch: ((last - dayAgo) / dayAgo) * 100, spark: c.slice(-24).map((x) => x.close) } }));
      }).catch(() => {}));
  const key = assets.join();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [key]);
  useInterval(load, 300000);
  useEffect(() => {
    if (!assets.length) return;
    // live last price and 24h change from Binance's public mini-ticker stream
    const streams = assets.map((a) => `${a.toLowerCase()}usdt@miniTicker`).join("/");
    const ws = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`);
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data)?.data;
      if (!m?.s?.endsWith("USDT")) return;
      const a = m.s.slice(0, -4), price = +m.c, open = +m.o;
      setTicks((t) => ({ ...t, [a]: { ...t[a], spark: t[a]?.spark ?? [], price, ch: open ? ((price - open) / open) * 100 : t[a]?.ch ?? 0 } }));
    };
    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return ticks;
}

function Spark({ values, up }: { values: number[]; up: boolean }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values), hi = Math.max(...values), w = 56, h = 18;
  const d = values.map((v, i) => `${i ? "L" : "M"}${((i / (values.length - 1)) * w).toFixed(1)} ${(h - 2 - ((v - lo) / (hi - lo || 1)) * (h - 4)).toFixed(1)}`).join(" ");
  return <svg width={w} height={h} className={up ? "text-up" : "text-down"} aria-hidden="true"><path d={d} fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>;
}

// ---------- top bar ----------
export function TopBar({ assets, asset, setAsset, ticks, facts, state, runs, runId, dark, toggle, onLearn, refresh }: {
  assets: string[]; asset: string; setAsset: (a: string) => void; ticks: Record<string, Tick>; facts: any; state: DeskState | null;
  runs: Run[]; runId: string | null; dark: boolean; toggle: () => void; onLearn: () => void; refresh: () => void;
}) {
  const [syncing, setSyncing] = useState(false);
  const eq = state?.equity.at(-1)?.value;
  const f = facts?.[asset];
  const sync = async () => {
    setSyncing(true);
    try { await api("/api/sync", "POST"); toast.success("Synced"); } catch (e: any) { toast.error(e.message); }
    setSyncing(false);
    refresh();
  };
  const live = state?.mode === "live";
  return (
    <header className="flex h-12 shrink-0 items-stretch border-b border-line bg-panel">
      <div className="flex items-center gap-2 border-r border-line px-3">
        <Avatar id="bull" size={26} mood="awake" />
        <span className="font-heading text-[15px] font-bold tracking-tight">tradedesk</span>
        {state && (
          <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider uppercase", live ? "bg-down/15 text-down" : "bg-brand-soft text-brand-strong")}>
            {state.mode}{state.market === "futures" ? " · futures" : ""}
          </span>
        )}
      </div>
      <nav className="flex min-w-0 items-stretch overflow-x-auto" aria-label="Markets">
        {assets.map((a) => {
          const t = ticks[a];
          const active = a === asset;
          return (
            <button key={a} type="button" onClick={() => setAsset(a)} aria-pressed={active}
              className={cn("relative flex items-center gap-3 border-r border-line px-3.5 text-left transition-colors hover:bg-raised/60", active && "bg-raised")}>
              {active && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-brand" />}
              <span>
                <span className="block text-[11px] font-semibold text-dim">{a}/USDT</span>
                <span className="block font-mono text-[13px] font-medium tabular-nums">{t ? px(t.price) : px(facts?.[a]?.price)}</span>
              </span>
              <span className={cn("font-mono text-xs tabular-nums", tone(t?.ch))}>{t ? pc(t.ch, 2) : ""}</span>
              {t && <Spark values={t.spark} up={t.ch >= 0} />}
            </button>
          );
        })}
      </nav>
      {f?.frames && (
        <dl className="hidden items-center gap-5 px-4 text-xs xl:flex">
          {[
            ["7d", <span className={tone(f.change?.["7d"])}>{pc(f.change?.["7d"])}</span>],
            ["RSI 1d", f.frames["1d"]?.rsi?.toFixed(0)],
            ["ATR 1d", `${f.frames["1d"]?.atr_pct?.toFixed(1)}%`],
            ["Funding", f.derivatives ? `${f.derivatives.funding_pct.toFixed(4)}%` : "–"],
            ["L/S", f.derivatives ? f.derivatives.long_short_ratio.toFixed(2) : "–"],
          ].map(([k, v], i) => (
            <div key={i}><dt className="text-[10px] text-dim">{k}</dt><dd className="font-mono tabular-nums">{v}</dd></div>
          ))}
        </dl>
      )}
      <div className="ml-auto flex items-center gap-1.5 px-3">
        <div className="mr-2 hidden text-right md:block">
          <p className="text-[10px] text-dim">Equity</p>
          <p className="font-mono text-[13px] font-medium tabular-nums">{eq == null ? "–" : `${px(eq)} ${state?.quote}`}</p>
        </div>
        {(() => {
          const latest = runs.find((r) => r.id === runId);
          const live = latest?.status === "running";
          return (
            <span className={cn("mr-1 hidden items-center gap-1.5 rounded-md px-2 py-1 text-xs sm:flex", live ? "bg-up/12 text-up" : "bg-sunk text-dim")}>
              <span className={cn("size-1.5 rounded-full", live ? "animate-pulse bg-up" : "bg-dim/60")} />
              {live ? "Desk working" : latest ? `Idle · last run ${clock(latest.started_at)}` : "No runs yet"}
            </span>
          );
        })()}
        <Button variant="ghost" size="icon" className="size-8" onClick={onLearn} aria-label="Glossary"><BookOpen className="size-4" /></Button>
        <Button variant="ghost" size="icon" className="size-8" onClick={toggle} aria-label={dark ? "Light theme" : "Dark theme"}>{dark ? <Sun className="size-4" /> : <Moon className="size-4" />}</Button>
        <Button variant="ghost" size="icon" className="size-8" onClick={sync} disabled={syncing} aria-label="Sync with exchange"><RefreshCw className={cn("size-4", syncing && "animate-spin")} /></Button>
      </div>
    </header>
  );
}

// ---------- chart / floor ----------
export function MainPanel({ asset, facts, run, events, fresh, onPick }: {
  asset: string; facts: any; run: Run | undefined; events: DeskEvent[]; fresh: DeskEvent[]; onPick: (id: string) => void;
}) {
  const [view, setView] = useState<"overview" | "chart" | "floor" | "report">("overview");
  const [tf, setTf] = useState<"4h" | "1d" | "1w">("1d");
  const [emas, setEmas] = useState(true);
  const f = facts?.[asset];
  const r = f?.frames ? readAsset(asset, f) : null;
  const working = events.length > 0 && run?.status === "running";
  return (
    <Panel
      className="h-full"
      title={<Seg value={view} onChange={setView} size="md" options={[{ v: "overview", label: "Overview" }, { v: "chart", label: "Chart" }, { v: "floor", label: <span className="flex items-center gap-1.5">Desk{working && <span className="size-1.5 animate-pulse rounded-full bg-up" />}</span> }, { v: "report", label: "Report" }]} />}
      right={view === "overview" ? (
        <span className="text-xs text-dim">FRED · CoinGecko · DefiLlama · alternative.me</span>
      ) : view === "chart" ? (
        <>
          <Seg value={tf} onChange={setTf} options={(["4h", "1d", "1w"] as const).map((x) => ({ v: x, label: <span className="flex items-center gap-1">{x}{r && <span className={cn("text-[10px]", r.trends[x].dir === "up" ? "text-up" : r.trends[x].dir === "down" ? "text-down" : "text-dim")}>{{ up: "▲", down: "▼", range: "▸", none: "" }[r.trends[x].dir as string]}</span>}</span> }))} />
          <button type="button" onClick={() => setEmas((e) => !e)} aria-pressed={emas}
            className={cn("ml-1 flex h-7 items-center gap-1.5 rounded-md px-2 text-xs", emas ? "text-fg" : "text-dim")}>
            <span className="flex gap-0.5"><i className="h-0.5 w-2 bg-[var(--ema20)]" /><i className="h-0.5 w-2 bg-[var(--ema50)]" /><i className="h-0.5 w-2 bg-[var(--ema200)]" /></span>EMA
          </button>
        </>
      ) : (
        <span className="text-xs text-dim">{run ? (run.status === "running" ? "running" : `run ${runLabel(run.id)}`) : ""}</span>
      )}
      bodyClass="relative"
    >
      {view === "chart" ? (
        <div className="absolute inset-0 pt-1">
          <PriceChart asset={asset} tf={tf} levels={f?.levels?.[tf === "1w" ? "1d" : tf]} height="100%" emas={emas} />
        </div>
      ) : view === "report" ? (
        <ReportView />
      ) : view === "overview" ? (
        <OverviewView />
      ) : (
        <div className="absolute inset-0 overflow-auto p-3">
          <Floor runId={run?.id ?? null} finished={run?.status !== "running"} events={events} fresh={fresh} onPick={onPick} hideSteps />
        </div>
      )}
    </Panel>
  );
}

// ---------- right side ----------
export function Signals({ asset, facts }: { asset: string; facts: any }) {
  const f = facts?.[asset];
  const m = readMood(facts?._market);
  if (!f?.frames) return <Panel title="Signals"><p className="p-3 text-xs text-dim">No snapshot in this run.</p></Panel>;
  const r = readAsset(asset, f);
  return (
    <Panel className="min-h-0 flex-1 basis-0" title={`Signals · ${asset}`} right={<span className="font-mono text-[11px] text-dim">snapshot</span>} bodyClass="overflow-y-auto">
      <p className="border-b border-line px-3 py-2 text-[13px] leading-snug">{r.headline}</p>
      <dl className="divide-y divide-line/60">
        {r.lines.map((l) => (
          <Explain key={l.key} term={l.term} text={l.text}>
            <div tabIndex={0} className="flex cursor-help items-center justify-between gap-3 px-3 py-[7px] text-[13px] outline-none hover:bg-raised/60 focus-visible:bg-raised/60">
              <dt className="text-dim">{l.label}</dt>
              <dd className={cn("font-mono tabular-nums", l.tone === "up" && "text-up", l.tone === "down" && "text-down", l.tone === "warn" && "text-warn")}>{l.value}</dd>
            </div>
          </Explain>
        ))}
        {m && (
          <Explain term="feargreed" text={m.text}>
            <div tabIndex={0} className="flex cursor-help items-center justify-between gap-3 px-3 py-[7px] text-[13px] outline-none hover:bg-raised/60">
              <dt className="text-dim">Fear &amp; Greed</dt>
              <dd className="flex items-center gap-2">
                <span className="relative h-1.5 w-16 overflow-hidden rounded-full bg-gradient-to-r from-down via-warn to-up">
                  <span className="absolute top-0 h-full w-0.5 bg-fg" style={{ left: `${m.value}%` }} />
                </span>
                <span className="font-mono tabular-nums">{m.value}</span>
              </dd>
            </div>
          </Explain>
        )}
      </dl>
    </Panel>
  );
}

const ORDER = ["prices", "headlines", "book", "technical", "news", "bull", "bear", "pm", "risk", "exchange"];

export function DeskRail({ events, run, onPick }: { events: DeskEvent[]; run: Run | undefined; onPick: (id: string) => void }) {
  const last = useMemo(() => {
    const m: Record<string, DeskEvent> = {};
    for (const e of events) if (CAST[e.actor]) m[e.actor] = e;
    return m;
  }, [events]);
  const pm = [...events].reverse().find((e) => e.actor === "pm" && e.kind !== "start" && e.body);
  const verdict = pm ? ((pm.body?.match(/^#\s*(.+)$/m)?.[1] ?? pm.title).split(":").pop() || "").trim() : null;
  const doneCount = ORDER.filter((a) => last[a] && last[a].kind !== "start").length;
  return (
    <Panel className="h-full" title="Desk" right={<span className="font-mono text-[11px] text-dim">{doneCount}/{ORDER.length}</span>} bodyClass="flex flex-col">
      <div className="h-0.5 bg-sunk"><div className="h-full bg-brand transition-[width] duration-500" style={{ width: `${(doneCount / ORDER.length) * 100}%` }} /></div>
      {verdict && (
        <button type="button" onClick={() => onPick("pm")} className="flex items-center gap-3 border-b border-line px-3 py-2.5 text-left hover:bg-raised/60">
          <span className="text-[11px] text-dim uppercase">Call</span>
          <span className="font-heading text-lg font-semibold capitalize">{verdict}</span>
          <span className="ml-auto text-[11px] text-dim">{clock(pm!.ts)}</span>
        </button>
      )}
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {ORDER.map((a) => {
          const e = last[a];
          const mood = !e ? "idle" : e.kind === "start" ? (run?.status === "running" ? "working" : "awake") : e.kind === "reject" || e.kind === "error" ? "alert" : "done";
          return (
            <li key={a}>
              <button type="button" onClick={() => onPick(a)} className="group flex w-full items-center gap-2.5 px-3 py-1.5 text-left hover:bg-raised/60">
                <Avatar id={a} size={26} mood={mood} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-[13px] font-medium">
                    {CAST[a].name}
                    <span className={cn("size-1.5 rounded-full", { idle: "bg-dim/40", working: "animate-pulse bg-brand", awake: "bg-dim/40", done: "bg-up", alert: "bg-down" }[mood])} />
                  </span>
                  <span className="block truncate text-xs text-dim">{e ? said(e) : "–"}</span>
                </span>
                <ChevronRight className="size-3.5 text-dim opacity-0 group-hover:opacity-100" />
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ---------- bottom tabs ----------
function Th({ children, right }: { children?: ReactNode; right?: boolean }) {
  return <th scope="col" className={cn("sticky top-0 bg-panel px-3 py-1.5 text-[11px] font-medium text-dim", right ? "text-right" : "text-left")}>{children}</th>;
}
function Td({ children, right, className }: { children?: ReactNode; right?: boolean; className?: string }) {
  return <td className={cn("px-3 py-1.5 whitespace-nowrap", right && "text-right font-mono tabular-nums", className)}>{children}</td>;
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="px-3 py-6 text-center text-xs text-dim">{children}</p>;
}

export function BottomTabs({ state, events, refresh, onPick }: { state: DeskState | null; events: DeskEvent[]; refresh: () => void; onPick: (id: string) => void }) {
  const plans = state?.plans ?? [], positions = state?.positions ?? [], closed = state?.closed ?? [];
  const waiting = plans.filter((p) => p.status === "proposed").length;
  const [tab, setTab] = useState<"plans" | "positions" | "history" | "log">("positions");
  useEffect(() => { if (waiting) setTab("plans"); }, [waiting]);
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const act = async (path: string, id: string, ok: string) => {
    setBusy(id);
    try { await api(path, "POST"); toast.success(ok); } catch (e: any) { toast.error(e.message); }
    setBusy(null);
    refresh();
  };
  const log = events.filter((e) => CAST[e.actor] && e.kind !== "start");
  const count = (n: number) => (n ? <span className="ml-1 rounded bg-sunk px-1 font-mono text-[10px]">{n}</span> : null);

  return (
    <Panel
      className="h-full"
      title={<Seg value={tab} onChange={setTab} options={[
        { v: "positions", label: <>Positions{count(positions.length)}</> },
        { v: "plans", label: <>Plans{waiting ? <span className="ml-1 rounded bg-brand px-1 font-mono text-[10px] text-brand-fg">{waiting}</span> : count(plans.length)}</> },
        { v: "history", label: <>History{count(closed.length)}</> },
        { v: "log", label: <>Log{count(log.length)}</> },
      ]} />}
      bodyClass="overflow-auto"
    >
      {tab === "positions" && (positions.length ? (
        <table className="w-full text-[13px]">
          <thead><tr><Th>Market</Th><Th>Side</Th><Th right>Size</Th><Th right>Entry</Th><Th right>Mark</Th><Th right>Stop</Th><Th right>Target</Th><Th right>PnL</Th><Th /></tr></thead>
          <tbody className="divide-y divide-line/60">
            {positions.map((p) => {
              const s = p.side === "long" ? 1 : -1;
              const pnl = p.price == null ? 0 : (p.price - p.entry_price) * p.qty * s;
              return (
                <tr key={p.id} className="hover:bg-raised/50">
                  <Td className="font-medium">{p.asset}/USDT <span className="text-[11px] text-dim">{p.horizon}</span>{p.venue === "futures" && <span className="ml-1.5 rounded bg-warn/12 px-1 py-px text-[10px] font-medium text-warn">futures{p.leverage > 1 ? ` ${p.leverage}x` : ""}</span>}</Td>
                  <Td className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</Td>
                  <Td right>{px(p.qty)}</Td><Td right>{px(p.entry_price)}</Td><Td right>{px(p.price)}</Td>
                  <Td right className="text-down">{px(p.stop)}</Td><Td right className="text-up">{px(p.take_profit)}</Td>
                  <Td right className={tone(pnl)}>{money(pnl)}</Td>
                  <Td right><Button size="xs" variant="outline" disabled={busy === p.id}
                    onClick={() => confirm(`Close ${p.asset} at market?`) && act(`/api/positions/${p.id}/close`, p.id, "Closed")}>Close</Button></Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : <Empty>No open positions</Empty>)}

      {tab === "plans" && (plans.length ? (
        <table className="w-full text-[13px]">
          <thead><tr><Th>Market</Th><Th>Side</Th><Th>Term</Th><Th right>Entry</Th><Th right>Stop</Th><Th right>Target</Th><Th right>R/R</Th><Th right>Risk</Th><Th right>Conf.</Th><Th>Status</Th><Th /></tr></thead>
          <tbody className="divide-y divide-line/60">
            {plans.map((p: Plan) => (
              <Fragment key={p.id}>
                <tr className="cursor-pointer hover:bg-raised/50" onClick={() => setOpen(open === p.id ? null : p.id)}>
                  <Td className="font-medium">{p.asset}/USDT{p.venue === "futures" && <span className="ml-1.5 rounded bg-warn/12 px-1 py-px text-[10px] font-medium text-warn">futures{p.leverage > 1 ? ` ${p.leverage}x` : ""}</span>}</Td>
                  <Td className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</Td>
                  <Td className="text-dim">{p.horizon}</Td>
                  <Td right>{px(p.entry)}</Td><Td right className="text-down">{px(p.stop)}</Td><Td right className="text-up">{px(p.take_profit)}</Td>
                  <Td right>{p.reward_risk ?? "–"}</Td><Td right>{p.risk_amount ? Number(p.risk_amount).toFixed(2) : "–"}</Td><Td right>{p.confidence}</Td>
                  <Td><span className={cn("rounded px-1.5 py-0.5 text-[11px] font-medium", p.status === "proposed" ? "bg-brand-soft text-brand-strong" : p.status === "rejected" ? "bg-down/10 text-down" : "bg-sunk text-dim")}>{p.status === "proposed" ? "awaiting you" : p.status}</span></Td>
                  <Td right>{p.status === "proposed" && (
                    <span className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                      <Button size="xs" className="bg-up text-white hover:bg-up/90" disabled={busy === p.id} onClick={() => act(`/api/plans/${p.id}/approve`, p.id, "Sent with stop")}>Approve</Button>
                      <Button size="xs" variant="ghost" disabled={busy === p.id} onClick={() => act(`/api/plans/${p.id}/reject`, p.id, "Dropped")}>Drop</Button>
                    </span>
                  )}</Td>
                </tr>
                {open === p.id && (
                  <tr className="bg-sunk/50">
                    <td colSpan={11} className="space-y-1 px-3 py-2 text-[13px]">
                      <p>{planStory(p)}</p>
                      <p className="text-dim">{p.thesis}</p>
                      {p.reasons && <p className="text-down">{p.reasons}</p>}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      ) : <Empty>No plans in the last 3 days</Empty>)}

      {tab === "history" && (closed.length ? (
        <table className="w-full text-[13px]">
          <thead><tr><Th>Closed</Th><Th>Market</Th><Th>Side</Th><Th right>Entry</Th><Th right>Exit</Th><Th>Reason</Th><Th right>PnL</Th></tr></thead>
          <tbody className="divide-y divide-line/60">
            {closed.map((p) => (
              <tr key={p.id} className="hover:bg-raised/50">
                <Td className="font-mono text-dim">{String(p.closed_at).slice(5, 16).replace("T", " ")}</Td>
                <Td className="font-medium">{p.asset}/USDT</Td>
                <Td className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</Td>
                <Td right>{px(p.entry_price)}</Td><Td right>{px(p.exit_price)}</Td>
                <Td className="text-dim">{p.exit_reason}</Td>
                <Td right className={tone(p.pnl)}>{money(p.pnl)}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <Empty>No closed trades yet</Empty>)}

      {tab === "log" && (log.length ? (
        <ul className="divide-y divide-line/60 text-[13px]">
          {[...log].reverse().map((e) => (
            <li key={e.id}>
              <details className="group">
                <summary className="flex cursor-pointer list-none items-center gap-2.5 px-3 py-1.5 hover:bg-raised/50">
                  <span className="w-11 font-mono text-[11px] text-dim">{clock(e.ts)}</span>
                  <button type="button" onClick={(ev) => { ev.preventDefault(); onPick(e.actor); }} aria-label={`Open ${CAST[e.actor].name}`}><Avatar id={e.actor} size={20} mood="awake" /></button>
                  <span className="w-20 shrink-0 font-medium">{CAST[e.actor].name}</span>
                  <span className={cn("min-w-0 flex-1 truncate", (e.kind === "reject" || e.kind === "error") && "text-down")}>{e.title}</span>
                  {e.html && <ChevronRight className="size-3.5 text-dim transition-transform group-open:rotate-90" />}
                </summary>
                {e.html && <Prose html={e.html} className="border-t border-line/60 bg-sunk/40 px-4 py-3 pl-[5.5rem] text-[13px]" />}
              </details>
            </li>
          ))}
        </ul>
      ) : <Empty>Nothing in this run yet</Empty>)}
    </Panel>
  );
}

// ---------- account ----------
export function AccountPanel({ state }: { state: DeskState | null }) {
  const vals = state?.equity ?? [];
  const eq = vals.at(-1)?.value, first = vals[0]?.value;
  const diff = eq != null && first != null ? eq - first : 0;
  const open = state?.positions.length ?? 0;
  const L = state?.limits;
  const pts = vals.map((v) => v.value);
  const lo = Math.min(...pts), hi = Math.max(...pts);
  const d = pts.length > 1 ? pts.map((v, i) => `${i ? "L" : "M"}${((i / (pts.length - 1)) * 100).toFixed(2)} ${(28 - ((v - lo) / (hi - lo || 1)) * 26).toFixed(2)}`).join(" ") : "M0 15 L100 15";
  return (
    <Panel title="Account" right={<span className="font-mono text-[11px] text-dim">{state?.auto_execute ? "auto" : "manual approve"}</span>}>
      <div className="space-y-2 px-3 py-2.5">
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-2xl font-medium tabular-nums">{eq == null ? "–" : eq.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          <span className={cn("font-mono text-xs tabular-nums", tone(diff))}>{money(diff)} ({first ? pc((diff / first) * 100, 2) : "0%"})</span>
        </div>
        <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="h-10 w-full text-brand" aria-label="Equity over time" role="img">
          <path d={`${d} L100 30 L0 30 Z`} fill="currentColor" opacity=".12" />
          <path d={d} fill="none" stroke="currentColor" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
        </svg>
        <dl className="grid grid-cols-3 gap-2 text-xs">
          <div><dt className="text-dim">Open</dt><dd className="font-mono">{open}/{L?.max_open_positions ?? "–"}</dd></div>
          <div><dt className="text-dim">Risk/trade</dt><dd className="font-mono">{L ? `${L.risk_per_trade_pct}%` : "–"}</dd></div>
          <div><dt className="text-dim">Day stop</dt><dd className="font-mono">{L ? `−${L.daily_loss_limit_pct}%` : "–"}</dd></div>
        </dl>
      </div>
    </Panel>
  );
}

// ---------- footer ----------
export function Footer({ ticks, assets, run }: { ticks: Record<string, Tick>; assets: string[]; run: Run | undefined }) {
  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 border-t border-line bg-panel px-3 text-[11px]">
      <span className="flex items-center gap-1.5 text-up"><span className="size-1.5 rounded-full bg-up" />Connected</span>
      <span className="text-dim">{run ? `Last run ${runLabel(run.id)} · ${run.status}` : "No runs"}</span>
      <div className="ml-auto flex gap-4 font-mono">
        {assets.map((a) => ticks[a] && (
          <span key={a}><span className="text-dim">{a}</span> {px(ticks[a].price)} <span className={tone(ticks[a].ch)}>{pc(ticks[a].ch, 2)}</span></span>
        ))}
      </div>
    </footer>
  );
}

export { Panel };

// ---------- report ----------
type Report = {
  since: string | null; start_equity: number; equity: { ts: string; value: number }[];
  runs: (Run & { call: string | null })[]; plans: (Plan & { replay: { outcome: string; r: number; pnl: number } })[];
  closed: any[]; realized: number;
};

const OUTCOME: Record<string, string> = { target: "text-up", stop: "text-down", open: "text-fg", waiting: "text-dim", expired: "text-dim" };

export function ReportView() {
  const [rep, setRep] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api<Report>("/api/report").then((r) => { setRep(r); setErr(null); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  useInterval(load, 60000);
  if (err) return <Empty>Report failed: {err}</Empty>;
  if (!rep) return <Empty>Loading…</Empty>;
  const eq = rep.equity.at(-1)?.value ?? rep.start_equity;
  const taken = rep.plans.filter((p) => ["placed", "approved", "filled", "closed"].includes(p.status) || p.exchange);
  const resolved = rep.plans.filter((p) => p.replay.outcome === "target" || p.replay.outcome === "stop");
  const wins = resolved.filter((p) => p.replay.outcome === "target").length;
  const hypo = rep.plans.reduce((s, p) => s + (p.replay.pnl || 0), 0);
  const hypoR = rep.plans.reduce((s, p) => s + (p.replay.r || 0), 0);
  const kpis: [string, ReactNode, string?][] = [
    ["Equity", `${px(eq)}`, `from ${px(rep.start_equity)}`],
    ["Net PnL", <span className={tone(eq - rep.start_equity)}>{money(eq - rep.start_equity)}</span>, pc(((eq - rep.start_equity) / rep.start_equity) * 100, 2)],
    ["Runs", rep.runs.length, rep.since ? `since ${runLabel(rep.since.slice(0, 16).replace(/[-:]/g, "").replace(/^(\d{4})(\d\d)(\d\d)T(\d{4}).*/, "$1-$2-$3T$4"))}` : ""],
    ["Ideas", rep.plans.length, `${taken.length} taken · ${rep.plans.filter((p) => p.status === "rejected").length} rejected`],
    ["Hit rate", resolved.length ? `${Math.round((wins / resolved.length) * 100)}%` : "–", `${wins}/${resolved.length} resolved`],
    ["All ideas, replayed", <span className={tone(hypo)}>{money(hypo)}</span>, `${hypoR >= 0 ? "+" : ""}${hypoR.toFixed(1)}R on real candles`],
  ];
  return (
    <div className="absolute inset-0 overflow-auto">
      <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-3 xl:grid-cols-6">
        {kpis.map(([k, v, sub]) => (
          <div key={k} className="bg-panel px-3 py-2.5">
            <p className="text-[11px] text-dim">{k}</p>
            <p className="font-mono text-lg font-medium tabular-nums">{v}</p>
            {sub && <p className="truncate text-[11px] text-dim">{sub}</p>}
          </div>
        ))}
      </div>
      <h3 className="border-y border-line px-3 py-2 text-[11px] font-semibold tracking-[0.08em] text-dim uppercase">Ideas, replayed on 1h candles</h3>
      {rep.plans.length ? (
        <table className="w-full text-[13px]">
          <thead><tr><Th>Made</Th><Th>Market</Th><Th>Side</Th><Th>Desk</Th><Th right>Entry</Th><Th right>Stop</Th><Th right>Target</Th><Th>Outcome</Th><Th right>R</Th><Th right>PnL</Th></tr></thead>
          <tbody className="divide-y divide-line/60">
            {[...rep.plans].reverse().map((p) => (
              <tr key={p.id} className="hover:bg-raised/50" title={p.reasons || p.thesis}>
                <Td className="font-mono text-dim">{String(p.created_at).slice(5, 16).replace("T", " ")}</Td>
                <Td className="font-medium">{p.asset}</Td>
                <Td className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</Td>
                <Td className="text-dim">{p.status}</Td>
                <Td right>{px(p.entry)}</Td><Td right className="text-down">{px(p.stop)}</Td><Td right className="text-up">{px(p.take_profit)}</Td>
                <Td className={OUTCOME[p.replay.outcome]}>{p.replay.outcome}</Td>
                <Td right className={tone(p.replay.r)}>{p.replay.r ? p.replay.r.toFixed(2) : "–"}</Td>
                <Td right className={tone(p.replay.pnl)}>{p.replay.pnl ? money(p.replay.pnl) : "–"}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <Empty>No ideas yet.</Empty>}
      <h3 className="border-y border-line px-3 py-2 text-[11px] font-semibold tracking-[0.08em] text-dim uppercase">Runs</h3>
      <table className="w-full text-[13px]">
        <tbody className="divide-y divide-line/60">
          {[...rep.runs].reverse().map((r) => (
            <tr key={r.id}>
              <Td className="w-32 font-mono text-dim">{runLabel(r.id)}</Td>
              <Td className="w-20 text-dim">{r.status}</Td>
              <Td>{r.call ?? <span className="text-dim">no decision</span>}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------- news ----------
type Headline = { title: string; link: string; source: string; category: string; ts: number };
const STOP = new Set("The A An And Or Of In On At To For With From By As Is Are Was Were Be Has Have Had It Its This That These Those After Before Over Under Into New Says Say Said How Why What Who When Will Could Would Should May Might Not No Than More Most Up Down Out About Amid Against Your You We Our Their They He She His Her As Just Now Here Live Updates Week Day Year Today First Last Big".split(" "));

function ago(ts: number) {
  const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
  return m < 60 ? `${m}m` : m < 1440 ? `${Math.round(m / 60)}h` : `${Math.round(m / 1440)}d`;
}

function trending(items: Headline[]) {
  const recent = items.filter((h) => Date.now() / 1000 - h.ts < 12 * 3600);
  const count = new Map<string, number>();
  for (const h of recent) {
    const words = new Set(h.title.replace(/[‘’'"“”:,.!?()]/g, " ").split(/\s+/).filter((w) => /^[A-Z][A-Za-z$&-]{2,}$/.test(w) && !STOP.has(w)));
    for (const w of words) count.set(w, (count.get(w) ?? 0) + 1);
  }
  return [...count].filter(([, n]) => n >= 3).sort((a, b) => b[1] - a[1]).slice(0, 8);
}

const SOURCES = (asset: string) => [
  ["Charts & markets", [
    ["TradingView", `https://www.tradingview.com/chart/?symbol=BINANCE:${asset}USDT`],
    ["Binance", `https://www.binance.com/en/trade/${asset}_USDT`],
    ["CoinGecko", "https://www.coingecko.com/"],
    ["CoinGlass · funding, OI, liquidations", "https://www.coinglass.com/"],
  ]],
  ["Macro calendar", [
    ["Economic calendar", "https://www.investing.com/economic-calendar/"],
    ["FOMC meetings", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"],
    ["CME FedWatch · rate odds", "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"],
  ]],
  ["Flows & sentiment", [
    ["Bitcoin ETF flows · Farside", "https://farside.co.uk/btc/"],
    ["DefiLlama · on-chain TVL", "https://defillama.com/"],
    ["Fear & Greed index", "https://alternative.me/crypto/fear-and-greed-index/"],
  ]],
] as const;

export function NewsPanel({ asset }: { asset: string }) {
  const [items, setItems] = useState<Headline[]>([]);
  const [cat, setCat] = useState<string>("all");
  const [topic, setTopic] = useState<string | null>(null);
  const [, tick] = useState(0);
  const load = () => api<Headline[]>("/api/news").then(setItems).catch(() => {});
  useEffect(() => { load(); }, []);
  useInterval(() => { load(); tick((x) => x + 1); }, 120000);
  const top = useMemo(() => trending(items), [items]);
  const shown = items.filter((h) => (cat === "all" || h.category === cat) && (!topic || h.title.includes(topic))).slice(0, 80);
  return (
    <Panel
      className="h-full"
      title={<Seg value={cat} onChange={(v) => { setCat(v); setTopic(null); }} options={[
        { v: "all", label: "News" }, { v: "crypto", label: "Crypto" }, { v: "markets", label: "Markets" },
        { v: "world", label: "World" }, { v: "politics", label: "Politics" }, { v: "links", label: "Sources" },
      ]} />}
      bodyClass="overflow-y-auto"
    >
      {cat === "links" ? (
        <div className="space-y-3 p-3">
          {SOURCES(asset).map(([group, links]) => (
            <div key={group}>
              <p className="mb-1 text-[11px] text-dim">{group}</p>
              <ul className="grid gap-px">
                {links.map(([name, url]) => (
                  <li key={url}><a href={url} target="_blank" rel="noreferrer" className="flex items-center justify-between rounded px-2 py-1.5 text-[13px] hover:bg-raised">
                    {name}<ChevronRight className="size-3.5 text-dim" /></a></li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <>
          {top.length > 0 && (
            <div className="flex flex-wrap gap-1 border-b border-line px-3 py-2">
              <span className="mr-1 self-center text-[11px] text-dim">Trending</span>
              {top.map(([w, n]) => (
                <button key={w} type="button" onClick={() => setTopic(topic === w ? null : w)} aria-pressed={topic === w}
                  className={cn("rounded px-1.5 py-0.5 text-xs", topic === w ? "bg-brand text-brand-fg" : "bg-sunk text-fg hover:bg-raised")}>
                  {w} <span className="text-dim">{n}</span>
                </button>
              ))}
            </div>
          )}
          {!shown.length && <Empty>{items.length ? "Nothing for this filter" : "Loading headlines…"}</Empty>}
          <ul className="divide-y divide-line/60">
            {shown.map((h) => (
              <li key={h.link}>
                <a href={h.link} target="_blank" rel="noreferrer" className="group flex gap-3 px-3 py-2 hover:bg-raised/60">
                  <span className="w-8 shrink-0 pt-px text-right font-mono text-[11px] text-dim">{ago(h.ts)}</span>
                  <span className="min-w-0">
                    <span className="block text-[13px] leading-snug group-hover:text-brand-strong">{h.title}</span>
                    <span className="text-[11px] text-dim">{h.source}{Date.now() / 1000 - h.ts < 3600 && <span className="ml-1.5 text-up">● new</span>}</span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}
