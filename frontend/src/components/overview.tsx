import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { api, useInterval, type Candle } from "@/lib/api";
import { pc } from "@/lib/learn";
import { cn } from "@/lib/utils";

type Point = { d: string; v: number };
export type Driver = {
  id: string; name: string; group: string; unit: string; why: string; value: number | null; as_of: string | null;
  change_1w: number | null; change_1m: number | null; change_3m: number | null; series: Point[]; tilt: number; reason: string;
};
type Macro = {
  updated: string;
  regime: { label: string; score: number; tailwinds: number; headwinds: number; total: number };
  drivers: Driver[];
  crypto: { market_cap?: number; volume?: number; change_24h?: number; btc_dominance?: number; eth_dominance?: number };
  fear_greed: Point[];
};

export const big = (n?: number) => n == null ? "–" : n >= 1e12 ? `$${(n / 1e12).toFixed(2)}T` : n >= 1e9 ? `$${(n / 1e9).toFixed(0)}B` : `$${n.toFixed(0)}`;

function fmt(d: Driver) {
  const v = d.value;
  if (v == null) return "–";
  if (d.unit === "%") return `${v.toFixed(2)}%`;
  if (d.unit === "$bn") return v >= 1000 ? `$${(v / 1000).toFixed(2)}T` : `$${v.toFixed(0)}B`;
  if (d.unit === "$") return `$${v.toFixed(2)}`;
  return v >= 1000 ? v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : v.toFixed(2);
}

const TILT = {
  1: { label: "Tailwind", cls: "bg-up/12 text-up", line: "var(--up)" },
  0: { label: "Neutral", cls: "bg-sunk text-dim", line: "var(--t-dim)" },
  [-1]: { label: "Headwind", cls: "bg-down/12 text-down", line: "var(--down)" },
} as const;

export function DriverCard({ d }: { d: Driver }) {
  const t = TILT[(Math.sign(d.tilt) as 1 | 0 | -1)];
  const ch = d.change_1m;
  return (
    <HoverCard openDelay={150} closeDelay={50}>
      <HoverCardTrigger asChild>
        <div tabIndex={0} className="flex cursor-help flex-col bg-panel px-3 pt-2.5 outline-none hover:bg-raised/40 focus-visible:bg-raised/40">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-dim">{d.name}</span>
            <span className={cn("rounded px-1.5 py-px text-[10px] font-semibold uppercase", t.cls)}>{t.label}</span>
          </div>
          <div className="mt-0.5 flex items-baseline justify-between gap-2">
            <span className="font-mono text-lg font-medium tabular-nums">{fmt(d)}</span>
            <span className="font-mono text-xs tabular-nums">
              <span className={cn(d.change_1w == null ? "text-dim" : d.change_1w >= 0 ? "text-up" : "text-down")}>{pc(d.change_1w)}</span>
              <span className="mr-2 text-dim"> 1w</span>
              <span className={cn(ch == null ? "text-dim" : ch >= 0 ? "text-up" : "text-down")}>{pc(ch)}</span>
              <span className="text-dim"> 1m</span>
            </span>
          </div>
          <div className="-mx-3 h-12">
            {d.series.length > 1 && (
              <ChartContainer config={{ v: { label: d.name, color: t.line } }} className="aspect-auto h-12 w-full">
                <AreaChart data={d.series} margin={{ top: 4, bottom: 0, left: 0, right: 0 }}>
                  <defs>
                    <linearGradient id={`g-${d.id}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--color-v)" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="var(--color-v)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <YAxis hide domain={["dataMin", "dataMax"]} />
                  <Area dataKey="v" type="monotone" stroke="var(--color-v)" strokeWidth={1.5} fill={`url(#g-${d.id})`} isAnimationActive={false} />
                </AreaChart>
              </ChartContainer>
            )}
          </div>
        </div>
      </HoverCardTrigger>
      <HoverCardContent side="bottom" className="w-72 space-y-1.5 p-3 text-[13px] leading-snug">
        <p className="font-semibold">{d.name} <span className="font-normal text-dim">· {d.group}</span></p>
        <p>{d.why}</p>
        <p className="text-dim">Now: {d.reason}. 3 months: {pc(d.change_3m)}. Data as of {d.as_of}.</p>
      </HoverCardContent>
    </HoverCard>
  );
}

export function Compare({ sp }: { sp?: Driver }) {
  const [btc, setBtc] = useState<Candle[]>([]);
  useEffect(() => { api<Candle[]>("/api/candles/BTC?tf=1d&limit=120").then(setBtc).catch(() => {}); }, []);
  const data = useMemo(() => {
    if (!btc.length || !sp?.series.length) return [];
    const spMap = new Map(sp.series.map((p) => [p.d, p.v]));
    const rows: { d: string; btc: number; sp?: number }[] = [];
    const b0 = btc[Math.max(0, btc.length - 90)].close;
    let s0: number | undefined, lastSp: number | undefined;
    for (const c of btc.slice(-90)) {
      const d = new Date(c.time * 1000).toISOString().slice(0, 10);
      const s = spMap.get(d) ?? lastSp;
      if (s != null) { lastSp = s; s0 ??= s; }
      rows.push({ d, btc: (c.close / b0) * 100, sp: s != null && s0 ? (s / s0) * 100 : undefined });
    }
    return rows;
  }, [btc, sp]);
  if (!data.length) return <div className="h-full animate-pulse bg-sunk/40" />;
  return (
    <ChartContainer config={{ btc: { label: "Bitcoin", color: "#f7931a" }, sp: { label: "S&P 500", color: "var(--brand)" } }} className="aspect-auto h-full w-full">
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="d" tickLine={false} axisLine={false} minTickGap={40} tickFormatter={(d) => new Date(d).toLocaleDateString([], { month: "short", day: "numeric" })} />
        <YAxis tickLine={false} axisLine={false} width={36} domain={["auto", "auto"]} tickFormatter={(v) => `${Math.round(v)}`} />
        <ReferenceLine y={100} stroke="var(--t-line)" />
        <ChartTooltip content={<ChartTooltipContent formatter={(v, n) => <span className="font-mono">{n === "btc" ? "Bitcoin" : "S&P 500"} {(Number(v) - 100).toFixed(1)}%</span>} />} />
        <Line dataKey="btc" type="monotone" stroke="var(--color-btc)" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line dataKey="sp" type="monotone" stroke="var(--color-sp)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
      </LineChart>
    </ChartContainer>
  );
}

export function FearGreed({ series }: { series: Point[] }) {
  const last = series.at(-1)?.v;
  const color = last == null ? "var(--t-dim)" : last < 25 ? "var(--down)" : last < 45 ? "var(--warn)" : last <= 55 ? "var(--t-dim)" : "var(--up)";
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-baseline justify-between px-3 pt-2">
        <span className="text-xs text-dim">Fear &amp; Greed, 120 days</span>
        <span className="font-mono text-lg tabular-nums" style={{ color }}>{last ?? "–"}</span>
      </div>
      <ChartContainer config={{ v: { label: "Fear & Greed", color } }} className="aspect-auto min-h-0 w-full flex-1">
        <AreaChart data={series} margin={{ top: 6, bottom: 0, left: 0, right: 0 }}>
          <YAxis hide domain={[0, 100]} />
          <ReferenceLine y={25} stroke="var(--down)" strokeDasharray="2 4" />
          <ReferenceLine y={75} stroke="var(--up)" strokeDasharray="2 4" />
          <ChartTooltip content={<ChartTooltipContent hideIndicator labelFormatter={(_, p) => p?.[0]?.payload?.d} />} />
          <Area dataKey="v" type="monotone" stroke="var(--color-v)" strokeWidth={1.5} fill="var(--color-v)" fillOpacity={0.12} isAnimationActive={false} />
        </AreaChart>
      </ChartContainer>
    </div>
  );
}

export function OverviewView() {
  const [m, setM] = useState<Macro | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api<Macro>("/api/macro").then((x) => { setM(x); setErr(null); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  useInterval(load, 15 * 60 * 1000);
  if (err && !m) return <p className="p-6 text-center text-xs text-dim">Macro data unavailable: {err}</p>;
  if (!m) return <div className="absolute inset-0 animate-pulse bg-sunk/30" />;
  const r = m.regime;
  const tone = r.label === "Risk-on" ? "text-up" : r.label === "Risk-off" ? "text-down" : "text-warn";
  const head = m.drivers.filter((d) => d.tilt < 0).map((d) => d.name);
  const tail = m.drivers.filter((d) => d.tilt > 0).map((d) => d.name);
  const sp = m.drivers.find((d) => d.id === "SP500");
  const c = m.crypto;
  return (
    <div className="absolute inset-0 flex flex-col overflow-y-auto">
      <div className="grid shrink-0 gap-px bg-line md:grid-cols-[1.3fr_repeat(4,minmax(0,1fr))]">
        <div className="bg-panel px-4 py-3">
          <p className="text-[11px] font-semibold tracking-[0.08em] text-dim uppercase">Macro regime for crypto</p>
          <p className={cn("font-heading text-2xl font-semibold", tone)}>{r.label}</p>
          <div className="mt-1 flex h-1.5 overflow-hidden rounded-full bg-sunk" aria-label={`${r.tailwinds} tailwinds, ${r.headwinds} headwinds of ${r.total}`}>
            <span className="bg-up" style={{ width: `${(r.tailwinds / r.total) * 100}%` }} />
            <span className="bg-dim/40" style={{ width: `${((r.total - r.tailwinds - r.headwinds) / r.total) * 100}%` }} />
            <span className="bg-down" style={{ width: `${(r.headwinds / r.total) * 100}%` }} />
          </div>
          <p className="mt-1.5 text-xs leading-snug text-dim">
            {r.tailwinds} tailwind{r.tailwinds === 1 ? "" : "s"}{tail.length ? ` (${tail.join(", ")})` : ""}, {r.headwinds} headwind{r.headwinds === 1 ? "" : "s"}{head.length ? ` (${head.join(", ")})` : ""}.
          </p>
        </div>
        {[
          ["Crypto market cap", big(c.market_cap), c.change_24h != null ? <span className={c.change_24h >= 0 ? "text-up" : "text-down"}>{pc(c.change_24h, 2)} 24h</span> : null],
          ["24h volume", big(c.volume), <span className="text-dim">all coins</span>],
          ["BTC dominance", c.btc_dominance != null ? `${c.btc_dominance.toFixed(1)}%` : "–", <span className="text-dim">share of crypto value</span>],
          ["ETH dominance", c.eth_dominance != null ? `${c.eth_dominance.toFixed(1)}%` : "–", <span className="text-dim">share of crypto value</span>],
        ].map(([k, v, sub], i) => (
          <div key={i} className="bg-panel px-3 py-3">
            <p className="text-xs text-dim">{k}</p>
            <p className="font-mono text-xl font-medium tabular-nums">{v}</p>
            <p className="text-[11px]">{sub}</p>
          </div>
        ))}
      </div>
      <div className="grid shrink-0 gap-px border-t border-line bg-line sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
        {m.drivers.map((d) => <DriverCard key={d.id} d={d} />)}
      </div>
      <div className="grid min-h-[260px] flex-1 gap-px border-t border-line bg-line lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex min-h-[240px] flex-col bg-panel">
          <div className="flex items-baseline justify-between px-3 pt-2">
            <span className="text-xs text-dim">Bitcoin vs S&amp;P 500, last 90 days (start = 100)</span>
            <span className="text-[11px] text-dim">Moving together = macro is driving crypto</span>
          </div>
          <div className="min-h-0 flex-1 px-1 pb-1"><Compare sp={sp} /></div>
        </div>
        <div className="min-h-[200px] bg-panel"><FearGreed series={m.fear_greed} /></div>
      </div>
    </div>
  );
}
