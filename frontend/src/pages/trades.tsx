import { Fragment, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Box, Page } from "@/components/shell";
import { ReportView } from "@/components/terminal";
import { Term } from "@/components/term";
import { useDeskCtx } from "@/lib/desk-context";
import { planSize, planStory, px } from "@/lib/learn";
import { cn } from "@/lib/utils";

const money = (n: number) => `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(2)}`;
const TABS = ["Plans", "Positions", "History", "Replay"] as const;

function Th({ children, right }: { children?: ReactNode; right?: boolean }) {
  return <th scope="col" className={cn("bg-sunk/60 px-3 py-2 text-xs font-medium text-dim", right ? "text-right" : "text-left")}>{children}</th>;
}
function Td({ children, right, className }: { children?: ReactNode; right?: boolean; className?: string }) {
  return <td className={cn("px-3 py-2.5 whitespace-nowrap", right && "text-right font-mono tabular-nums", className)}>{children}</td>;
}

export default function Trades() {
  const d = useDeskCtx();
  const s = d.state;
  const plans = s?.plans ?? [], positions = s?.positions ?? [], closed = s?.closed ?? [];
  const waiting = plans.filter((p) => p.status === "proposed").length;
  const [tab, setTab] = useState<(typeof TABS)[number]>(waiting ? "Plans" : positions.length ? "Positions" : "Plans");
  const [open, setOpen] = useState<string | null>(null);
  const [stops, setStops] = useState<Record<string, string>>({});
  const counts: Record<string, number> = { Plans: plans.length, Positions: positions.length, History: closed.length, Replay: 0 };
  const wins = closed.filter((p) => p.pnl > 0).length;
  const realized = closed.reduce((a, p) => a + (p.pnl || 0), 0);

  return (
    <Page>
      <section className="grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4">
        {[
          ["Waiting for you", waiting, waiting ? "text-brand-strong" : ""],
          ["Open positions", positions.length, ""],
          ["Closed trades", closed.length, ""],
          ["Realized", `${money(realized)} ${s?.quote ?? ""}`, realized >= 0 ? "text-up" : "text-down"],
        ].map(([k, v, c]) => (
          <div key={k as string} className="bg-panel p-4">
            <p className="text-xs text-dim">{k}</p>
            <p className={cn("mt-1 font-mono text-2xl tabular-nums", c as string)}>{v}</p>
            {k === "Closed trades" && closed.length > 0 && <p className="text-xs text-dim">{Math.round((wins / closed.length) * 100)}% winners</p>}
          </div>
        ))}
      </section>

      <div className="flex gap-1 rounded-lg bg-sunk p-1 sm:w-fit">
        {TABS.map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)} aria-pressed={tab === t}
            className={cn("flex-1 rounded-md px-4 py-1.5 text-sm font-medium sm:flex-none", tab === t ? "bg-panel text-fg shadow-sm" : "text-dim hover:text-fg")}>
            {t}{counts[t] ? <span className="ml-1.5 font-mono text-xs text-dim">{counts[t]}</span> : null}
          </button>
        ))}
      </div>

      {tab === "Plans" && (
        <Box pad={false}>
          {plans.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead><tr><Th>Market</Th><Th>Side</Th><Th>Term</Th><Th right>Entry</Th><Th right>Stop</Th><Th right>Target</Th><Th right>Size</Th><Th right><Term k="rr">R/R</Term></Th><Th right>Risk</Th><Th right><Term k="confidence">Conf.</Term></Th><Th>Status</Th><Th /></tr></thead>
                <tbody className="divide-y divide-line/60">
                  {plans.map((p) => (
                    <Fragment key={p.id}>
                      <tr className="cursor-pointer hover:bg-raised/40" onClick={() => setOpen(open === p.id ? null : p.id)}>
                        <Td className="font-semibold"><Link to={`/markets/${p.asset}`} onClick={(e) => e.stopPropagation()} className="hover:underline">{p.asset}</Link>{p.venue === "futures" && <span className="ml-1.5 rounded bg-warn/12 px-1 py-px text-[10px] font-medium text-warn">futures{p.leverage > 1 ? ` ${p.leverage}x` : ""}</span>}</Td>
                        <Td className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</Td>
                        <Td className="text-dim">{p.horizon}</Td>
                        <Td right>{px(p.entry)}</Td><Td right className="text-down">{px(p.stop)}</Td><Td right className="text-up">{px(p.take_profit)}</Td>
                        <Td right>{planSize(p).value ? <>{planSize(p).value.toFixed(2)}{planSize(p).lev > 1 && <span className="block text-[11px] text-dim">{planSize(p).margin.toFixed(2)} margin</span>}</> : "–"}</Td>
                        <Td right>{p.reward_risk ?? "–"}</Td><Td right>{p.risk_amount ? Number(p.risk_amount).toFixed(2) : "–"}</Td><Td right>{p.confidence}</Td>
                        <Td><span className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold", p.status === "proposed" ? "bg-brand-soft text-brand-strong" : p.status === "rejected" ? "bg-down/12 text-down" : "bg-sunk text-dim")}>{p.status === "proposed" ? "waiting for you" : p.status}</span></Td>
                        <Td right>{p.status === "proposed" && (
                          <span className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                            <Button size="xs" className="bg-up text-white hover:bg-up/90" onClick={() => d.act(`/api/plans/${p.id}/approve`, "POST", "Sent with its stop")}>Approve</Button>
                            <Button size="xs" variant="ghost" onClick={() => d.act(`/api/plans/${p.id}/reject`, "POST", "Dropped")}>Drop</Button>
                          </span>
                        )}</Td>
                      </tr>
                      {open === p.id && (
                        <tr className="bg-sunk/40"><td colSpan={11} className="space-y-1.5 px-4 py-3 text-[13px]">
                          <p>{planStory(p, s?.quote)}</p>
                          <p className="text-dim"><b className="text-fg">Why: </b>{p.thesis}</p>
                          <p className="text-dim"><b className="text-fg">Wrong if: </b>{p.invalidation}</p>
                          {p.reasons && <p className="text-down"><b>Risk engine: </b>{p.reasons}</p>}
                        </td></tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="p-8 text-center text-sm text-dim">No plans in the last three days.</p>}
        </Box>
      )}

      {tab === "Positions" && (
        <Box pad={false}>
          {positions.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead><tr><Th>Market</Th><Th>Side</Th><Th right>Size</Th><Th right>Value</Th><Th right>Entry</Th><Th right>Mark</Th><Th right>Stop</Th><Th right>Target</Th><Th right>PnL</Th><Th>Move stop</Th><Th /></tr></thead>
                <tbody className="divide-y divide-line/60">
                  {positions.map((p) => {
                    const sg = p.side === "long" ? 1 : -1;
                    const pnl = p.price == null ? 0 : (p.price - p.entry_price) * p.qty * sg;
                    return (
                      <tr key={p.id} className="hover:bg-raised/40">
                        <Td className="font-semibold"><Link to={`/markets/${p.asset}`} className="hover:underline">{p.asset}</Link> <span className="text-xs font-normal text-dim">{p.horizon}</span>{p.venue === "futures" && <span className="ml-1.5 rounded bg-warn/12 px-1 py-px text-[10px] font-medium text-warn">futures{p.leverage > 1 ? ` ${p.leverage}x` : ""}</span>}</Td>
                        <Td className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</Td>
                        <Td right>{px(p.qty)}</Td><Td right>{(p.qty * (p.price ?? p.entry_price)).toFixed(2)}</Td><Td right>{px(p.entry_price)}</Td><Td right>{px(p.price)}</Td>
                        <Td right className="text-down">{px(p.stop)}</Td><Td right className="text-up">{px(p.take_profit)}</Td>
                        <Td right className={pnl >= 0 ? "text-up" : "text-down"}>{money(pnl)}</Td>
                        <Td>
                          <form className="flex gap-1" onSubmit={(e) => { e.preventDefault(); const v = Number(stops[p.id]); if (v) d.act(`/api/positions/${p.id}/stop?price=${v}`, "POST", "Stop moved"); }}>
                            <Input value={stops[p.id] ?? ""} onChange={(e) => setStops({ ...stops, [p.id]: e.target.value })} inputMode="decimal" placeholder={px(p.stop)} className="h-7 w-24 font-mono text-xs" aria-label="New stop price" />
                            <Button size="xs" variant="outline" type="submit">Set</Button>
                          </form>
                        </Td>
                        <Td right><Button size="xs" variant="outline" onClick={() => confirm(`Close ${p.asset} at market now?`) && d.act(`/api/positions/${p.id}/close`, "POST", "Closed")}>Close</Button></Td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="border-t border-line px-4 py-2 text-xs text-dim">Stops stay on Binance while this Mac is off.</p>
            </div>
          ) : <p className="p-8 text-center text-sm text-dim">No open positions.</p>}
        </Box>
      )}

      {tab === "History" && (
        <Box pad={false}>
          {closed.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead><tr><Th>Closed</Th><Th>Market</Th><Th>Side</Th><Th right>Entry</Th><Th right>Exit</Th><Th>Reason</Th><Th right>PnL</Th></tr></thead>
                <tbody className="divide-y divide-line/60">
                  {closed.map((p) => (
                    <tr key={p.id} className="hover:bg-raised/40">
                      <Td className="font-mono text-dim">{String(p.closed_at).slice(5, 16).replace("T", " ")}</Td>
                      <Td className="font-semibold">{p.asset}{p.venue === "futures" && <span className="ml-1.5 rounded bg-warn/12 px-1 py-px text-[10px] font-medium text-warn">futures{p.leverage > 1 ? ` ${p.leverage}x` : ""}</span>}</Td>
                      <Td className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</Td>
                      <Td right>{px(p.entry_price)}</Td><Td right>{px(p.exit_price)}</Td>
                      <Td className="text-dim">{p.exit_reason}</Td>
                      <Td right className={p.pnl >= 0 ? "text-up" : "text-down"}>{money(p.pnl)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="p-8 text-center text-sm text-dim">No closed trades yet.</p>}
        </Box>
      )}

      {tab === "Replay" && (
        <Box title="Idea replay on 1h candles" pad={false}>
          <div className="relative h-[70vh]"><ReportView /></div>
        </Box>
      )}
    </Page>
  );
}
