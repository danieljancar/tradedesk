import { useState } from "react";
import { Bar, BarChart, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Box } from "@/components/shell";
import { Term } from "@/components/term";

import { pc } from "@/lib/learn";
import { cn } from "@/lib/utils";
import { useApi } from "@/lib/query";

type Point = { t: number } & Record<string, number>;
type Data = { open_interest: Point[]; long_short: Point[]; top_traders: Point[]; taker: Point[]; funding: Point[] };
const PERIODS = ["1h", "4h", "1d"] as const;
const when = (t: number) => new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const usd = (v: number) => (v >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v.toFixed(0));

function change(rows: Point[], key: string) {
  if (rows.length < 2) return null;
  return (rows.at(-1)![key] / rows[0][key] - 1) * 100;
}

function Panel({ title, term, value, tone, note, children }: { title: string; term: string; value: string; tone?: string; note: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 bg-panel p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs text-dim"><Term k={term}>{title}</Term></p>
        <p className={cn("font-mono text-sm tabular-nums", tone)}>{value}</p>
      </div>
      <div className="mt-1 h-28">{children}</div>
      <p className="mt-1 text-xs leading-snug text-dim">{note}</p>
    </div>
  );
}

export function Positioning({ asset }: { asset: string }) {
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("4h");
  const q = useApi<Data>(`/api/positioning/${asset}?period=${period}`, { stale: 120_000 });
  const data = q.data ?? null;
  const error = q.data ? null : (q.error?.message ?? null);

  const empty = data && Object.values(data).every((s) => !s.length);
  const ls = (data?.long_short ?? []).map((p) => ({ t: p.t, accounts: p.accounts, positions: data?.top_traders.find((x) => x.t === p.t)?.positions }));
  const oiCh = data ? change(data.open_interest, "usd") : null;
  const fund = data?.funding.at(-1)?.pct;
  const acc = data?.long_short.at(-1)?.accounts;
  const top = data?.top_traders.at(-1)?.positions;
  const tk = data?.taker.slice(-6) ?? [];
  const tkAvg = tk.length ? tk.reduce((a, p) => a + p.ratio, 0) / tk.length : null;
  const axis = { tickLine: false, axisLine: false } as const;

  return (
    <Box title={`Futures positioning, ${asset}`} pad={false} right={
      <div className="flex rounded-md bg-sunk p-0.5">
        {PERIODS.map((p) => (
          <button key={p} type="button" onClick={() => setPeriod(p)} aria-pressed={period === p}
            className={cn("h-6 rounded-[5px] px-2.5 text-xs font-medium", period === p ? "bg-raised text-fg shadow-sm" : "text-dim hover:text-fg")}>{p}</button>
        ))}
      </div>
    }>
      {error && <p className="p-4 text-sm text-down">Binance did not answer: {error}</p>}
      {!data && !error && <div className="m-4 h-28 animate-pulse rounded-md bg-sunk" />}
      {empty && <p className="p-4 text-sm text-dim">Binance has no futures market for {asset}, so there is no positioning data.</p>}
      {data && !empty && (
        <div className="grid gap-px bg-line sm:grid-cols-2">
          <Panel title="Open interest" term="oi" value={data.open_interest.length ? `${usd(data.open_interest.at(-1)!.usd)} USD` : "–"} tone={oiCh == null ? "" : oiCh >= 0 ? "text-up" : "text-down"}
            note={oiCh == null ? "No history." : `${pc(oiCh)} over this window. ${oiCh > 5 ? "New money is betting." : oiCh < -5 ? "Bets are being closed." : "Little change in open bets."}`}>
            <ChartContainer config={{ usd: { label: "Open interest", color: "var(--brand)" } }} className="aspect-auto h-full w-full">
              <LineChart data={data.open_interest} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <XAxis dataKey="t" hide /><YAxis {...axis} width={44} domain={["auto", "auto"]} tickFormatter={usd} />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => when(Number(p?.[0]?.payload?.t))} formatter={(v) => <span className="font-mono">{usd(Number(v))} USD</span>} />} />
                <Line dataKey="usd" stroke="var(--color-usd)" strokeWidth={1.6} dot={false} isAnimationActive={false} />
              </LineChart>
            </ChartContainer>
          </Panel>
          <Panel title="Funding" term="funding" value={fund == null ? "–" : `${fund >= 0 ? "+" : ""}${fund.toFixed(4)}%`} tone={fund == null ? "" : fund > 0.03 ? "text-warn" : fund < 0 ? "text-down" : ""}
            note={fund == null ? "No funding history." : fund > 0.03 ? "Longs pay well above the 0.01% baseline, they are crowded." : fund < 0 ? "Shorts are paying, the crowd leans down." : "Near the 0.01% baseline, nobody is paying up."}>
            <ChartContainer config={{ pct: { label: "Funding", color: "var(--brand)" } }} className="aspect-auto h-full w-full">
              <BarChart data={data.funding} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <XAxis dataKey="t" hide /><YAxis {...axis} width={44} tickFormatter={(v) => `${Number(v).toFixed(3)}`} />
                <ReferenceLine y={0.01} stroke="var(--t-dim)" strokeDasharray="3 3" />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => when(Number(p?.[0]?.payload?.t))} formatter={(v) => <span className="font-mono">{Number(v).toFixed(4)}% per 8h</span>} />} />
                <Bar dataKey="pct" fill="var(--color-pct)" isAnimationActive={false} />
              </BarChart>
            </ChartContainer>
          </Panel>
          <Panel title="Long/short ratio" term="longshort" value={acc == null ? "–" : `${acc.toFixed(2)}${top != null ? `, top ${top.toFixed(2)}` : ""}`}
            note={acc == null ? "No history." : `Accounts ${acc > 1 ? "lean long" : "lean short"}${top != null ? `, top traders ${top > 1 ? "lean long" : "lean short"}` : ""}.${acc != null && top != null && acc > 1.5 && top < 1 ? " The crowd is long against the big accounts." : ""}`}>
            <ChartContainer config={{ accounts: { label: "All accounts", color: "var(--brand)" }, positions: { label: "Top traders", color: "var(--ema50)" } }} className="aspect-auto h-full w-full">
              <LineChart data={ls} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <XAxis dataKey="t" hide /><YAxis {...axis} width={44} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toFixed(1)} />
                <ReferenceLine y={1} stroke="var(--t-dim)" strokeDasharray="3 3" />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => when(Number(p?.[0]?.payload?.t))} formatter={(v, n) => <span className="font-mono">{n === "accounts" ? "All accounts" : "Top traders"} {Number(v).toFixed(2)}</span>} />} />
                <Line dataKey="accounts" stroke="var(--color-accounts)" strokeWidth={1.6} dot={false} isAnimationActive={false} />
                <Line dataKey="positions" stroke="var(--color-positions)" strokeWidth={1.6} strokeDasharray="4 3" dot={false} connectNulls isAnimationActive={false} />
              </LineChart>
            </ChartContainer>
          </Panel>
          <Panel title="Taker buy/sell" term="taker" value={tkAvg == null ? "–" : tkAvg.toFixed(2)} tone={tkAvg == null ? "" : tkAvg >= 1 ? "text-up" : "text-down"}
            note={tkAvg == null ? "No history." : `Average of the last ${tk.length} bars. ${tkAvg > 1.05 ? "Buyers are pushing." : tkAvg < 0.95 ? "Sellers are pushing." : "Neither side is pushing hard."}`}>
            <ChartContainer config={{ ratio: { label: "Buy/sell", color: "var(--up)" } }} className="aspect-auto h-full w-full">
              <LineChart data={data.taker} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <XAxis dataKey="t" hide /><YAxis {...axis} width={44} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toFixed(2)} />
                <ReferenceLine y={1} stroke="var(--t-dim)" strokeDasharray="3 3" />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => when(Number(p?.[0]?.payload?.t))} formatter={(v) => <span className="font-mono">{Number(v).toFixed(3)}</span>} />} />
                <Line dataKey="ratio" stroke="var(--color-ratio)" strokeWidth={1.6} dot={false} isAnimationActive={false} />
              </LineChart>
            </ChartContainer>
          </Panel>
        </div>
      )}
    </Box>
  );
}
