import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Box, Page } from "@/components/shell";
import { Term } from "@/components/term";
import { api } from "@/lib/api";
import { pc, px } from "@/lib/learn";
import { cn } from "@/lib/utils";

type Group = { count: number; pnl: number; win_rate: number; avg_r: number };
type Report = {
  quote: string;
  metrics: {
    days?: number; start?: string; end?: string; total_return_pct?: number | null; max_drawdown_pct?: number | null;
    current_drawdown_pct?: number | null; sharpe?: number | null; sortino?: number | null;
    best_day?: { d: string; pct: number } | null; worst_day?: { d: string; pct: number } | null;
  };
  trades: {
    count: number; win_rate?: number | null; profit_factor?: number | null; expectancy_r?: number | null; expectancy_quote?: number | null;
    avg_win_r?: number | null; avg_loss_r?: number | null; avg_hold_hours?: number | null; by?: Record<string, Record<string, Group>>;
  };
  equity: { d: string; value: number; drawdown_pct: number }[];
  benchmark: { d: string; btc: number; value: number }[];
  benchmark_note?: string | null;
};

const BY: [string, string][] = [["asset", "By asset"], ["horizon", "By horizon"], ["side", "Long and short"], ["sleeve", "By sleeve"], ["exit_reason", "How trades ended"]];
const LABEL: Record<string, string> = { target: "hit the target", stop: "hit the stop", manual: "closed by hand", timeout: "ran out of time", active: "trading", core: "core" };
const day = (d: string) => new Date(d).toLocaleDateString([], { month: "short", day: "numeric" });
const num = (n: number | null | undefined, digits = 2) => (n == null ? "n/a" : n.toFixed(digits));

function Stat({ label, term, value, sub, tone }: { label: string; term?: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="bg-panel p-4">
      <p className="text-xs text-dim">{term ? <Term k={term}>{label}</Term> : label}</p>
      <p className={cn("mt-1 font-mono text-2xl tabular-nums", tone)}>{value}</p>
      {sub && <p className="text-xs text-dim">{sub}</p>}
    </div>
  );
}

export default function Performance() {
  const [r, setR] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<Report>("/api/analytics").then(setR).catch((e) => setError(e.message)); }, []);
  if (error) return <Page><Box title="Performance"><p className="text-sm text-down">Couldn't load the numbers: {error}</p></Box></Page>;
  if (!r) return <Page><div className="h-40 animate-pulse rounded-xl bg-panel" /></Page>;

  const m = r.metrics, t = r.trades;
  const tone = (n?: number | null) => (n == null ? "" : n >= 0 ? "text-up" : "text-down");
  const btcStart = r.benchmark[0]?.value, deskEnd = r.equity.at(-1)?.value, btcEnd = r.benchmark.at(-1)?.value;
  const vsBtc = btcStart && deskEnd != null && btcEnd != null ? ((deskEnd - btcEnd) / btcStart) * 100 : null;
  const series = r.equity.map((e) => ({ d: e.d, desk: e.value, btc: r.benchmark.find((b) => b.d === e.d)?.value }));
  const few = t.count < 20;

  return (
    <Page>
      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-4">
        <Stat label="Return" value={pc(m.total_return_pct)} tone={tone(m.total_return_pct)} sub={m.days ? `${m.days} days, since ${day(m.start!)}` : "no equity history yet"} />
        <Stat label="Against holding BTC" value={vsBtc == null ? "n/a" : pc(vsBtc)} tone={tone(vsBtc)} sub="same money in BTC on day one" />
        <Stat label="Worst drop" term="drawdown" value={pc(m.max_drawdown_pct)} tone="text-down" sub={`now ${pc(m.current_drawdown_pct)} from the high`} />
        <Stat label="Sharpe ratio" term="sharpe" value={num(m.sharpe)} sub={`Sortino ${num(m.sortino)}`} />
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-4">
          <Box title="The desk against buying BTC and holding it" right={<span className="text-xs text-dim">{r.quote}, end of each day</span>} pad={false}>
            <div className="h-72 p-2">
              {series.length > 1 ? (
                <ChartContainer config={{ desk: { label: "Desk", color: "var(--brand)" }, btc: { label: "BTC held", color: "#f7931a" } }} className="aspect-auto h-full w-full">
                  <LineChart data={series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                    <CartesianGrid vertical={false} strokeDasharray="2 4" />
                    <XAxis dataKey="d" tickLine={false} axisLine={false} minTickGap={40} tickFormatter={day} />
                    <YAxis tickLine={false} axisLine={false} width={48} domain={["auto", "auto"]} tickFormatter={(v) => px(v)} />
                    <ChartTooltip content={<ChartTooltipContent labelFormatter={(d) => day(String(d))} formatter={(v, n) => <span className="font-mono">{n === "desk" ? "Desk" : "BTC held"} {px(Number(v))}</span>} />} />
                    <Line dataKey="desk" type="monotone" stroke="var(--color-desk)" strokeWidth={2} dot={false} isAnimationActive={false} />
                    <Line dataKey="btc" type="monotone" stroke="var(--color-btc)" strokeWidth={1.6} strokeDasharray="4 3" dot={false} connectNulls isAnimationActive={false} />
                  </LineChart>
                </ChartContainer>
              ) : <p className="p-4 text-sm text-dim">The curve starts once the desk has recorded equity on at least two days.</p>}
            </div>
            {r.benchmark_note && <p className="border-t border-line px-4 py-2 text-xs text-dim">{r.benchmark_note}</p>}
          </Box>

          <Box title={<Term k="drawdown">Distance from the last high</Term>} pad={false}>
            <div className="h-40 p-2">
              {r.equity.length > 1 && (
                <ChartContainer config={{ drawdown_pct: { label: "From the high", color: "var(--down)" } }} className="aspect-auto h-full w-full">
                  <AreaChart data={r.equity} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                    <XAxis dataKey="d" tickLine={false} axisLine={false} minTickGap={40} tickFormatter={day} />
                    <YAxis tickLine={false} axisLine={false} width={48} domain={["dataMin", 0]} tickFormatter={(v) => `${Number(v).toFixed(0)}%`} />
                    <ChartTooltip content={<ChartTooltipContent labelFormatter={(d) => day(String(d))} formatter={(v) => <span className="font-mono">{Number(v).toFixed(2)}% from the high</span>} />} />
                    <Area dataKey="drawdown_pct" type="monotone" stroke="var(--color-drawdown_pct)" fill="var(--color-drawdown_pct)" fillOpacity={0.18} isAnimationActive={false} />
                  </AreaChart>
                </ChartContainer>
              )}
            </div>
          </Box>

          {t.by && (
            <Box title="Closed trades, broken down">
              <div className="grid gap-6 md:grid-cols-2">
                {BY.filter(([k]) => t.by?.[k] && Object.keys(t.by[k]).length).map(([k, label]) => (
                  <div key={k}>
                    <p className="mb-1.5 text-xs font-medium text-dim">{label}</p>
                    <table className="w-full text-[13px]">
                      <thead><tr className="text-left text-xs text-dim"><th className="py-1 font-medium" /><th className="py-1 text-right font-medium">Trades</th><th className="py-1 text-right font-medium">Won</th><th className="py-1 text-right font-medium"><Term k="r">Avg R</Term></th><th className="py-1 text-right font-medium">P&amp;L</th></tr></thead>
                      <tbody className="divide-y divide-line/60">
                        {Object.entries(t.by![k]).sort((a, b) => b[1].pnl - a[1].pnl).map(([g, v]) => (
                          <tr key={g}>
                            <td className="py-1.5">{LABEL[g] ?? g}</td>
                            <td className="py-1.5 text-right font-mono">{v.count}</td>
                            <td className="py-1.5 text-right font-mono">{Math.round(v.win_rate * 100)}%</td>
                            <td className={cn("py-1.5 text-right font-mono", tone(v.avg_r))}>{num(v.avg_r)}</td>
                            <td className={cn("py-1.5 text-right font-mono", tone(v.pnl))}>{v.pnl >= 0 ? "+" : "−"}{Math.abs(v.pnl).toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
              </div>
            </Box>
          )}
        </div>

        <div className="space-y-4">
          <Box title="Trades">
            {!t.count ? <p className="text-sm text-dim">No closed trades yet.</p> : (
              <>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-[13px]">
                  <div><dt className="text-xs text-dim">Closed</dt><dd className="font-mono text-lg">{t.count}</dd></div>
                  <div><dt className="text-xs text-dim">Won</dt><dd className="font-mono text-lg">{t.win_rate != null ? `${Math.round(t.win_rate * 100)}%` : "n/a"}</dd></div>
                  <div><dt className="text-xs text-dim"><Term k="profit_factor">Profit factor</Term></dt><dd className="font-mono text-lg">{num(t.profit_factor)}</dd></div>
                  <div><dt className="text-xs text-dim"><Term k="expectancy">Per trade</Term></dt><dd className={cn("font-mono text-lg", tone(t.expectancy_r))}>{num(t.expectancy_r)} R</dd><dd className="text-xs text-dim">{t.expectancy_quote != null ? `${t.expectancy_quote >= 0 ? "+" : "−"}${Math.abs(t.expectancy_quote).toFixed(2)} ${r.quote}` : ""}</dd></div>
                  <div><dt className="text-xs text-dim">Average win</dt><dd className="font-mono text-up">{num(t.avg_win_r)} R</dd></div>
                  <div><dt className="text-xs text-dim">Average loss</dt><dd className="font-mono text-down">{num(t.avg_loss_r)} R</dd></div>
                  <div className="col-span-2"><dt className="text-xs text-dim">Average time in a trade</dt><dd className="font-mono">{t.avg_hold_hours != null ? (t.avg_hold_hours >= 48 ? `${(t.avg_hold_hours / 24).toFixed(1)} days` : `${t.avg_hold_hours.toFixed(0)} hours`) : "n/a"}</dd></div>
                </dl>
                {few && <p className="mt-4 rounded-md bg-warn/10 px-3 py-2 text-[13px] text-warn">{t.count} trades is too few to tell skill from luck. These numbers start to mean something after 30 or more.</p>}
              </>
            )}
          </Box>
          <Box title="Best and worst day">
            <dl className="space-y-2 text-[13px]">
              <div className="flex justify-between"><dt>Best</dt><dd className="font-mono text-up">{m.best_day ? `${pc(m.best_day.pct, 2)} on ${day(m.best_day.d)}` : "n/a"}</dd></div>
              <div className="flex justify-between"><dt>Worst</dt><dd className="font-mono text-down">{m.worst_day ? `${pc(m.worst_day.pct, 2)} on ${day(m.worst_day.d)}` : "n/a"}</dd></div>
            </dl>
          </Box>
        </div>
      </div>
    </Page>
  );
}
