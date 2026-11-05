import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Box, Page } from "@/components/shell";
import { Term } from "@/components/term";
import { api, useInterval } from "@/lib/api";
import { useDeskCtx } from "@/lib/desk-context";
import { pc, px } from "@/lib/learn";
import { cn } from "@/lib/utils";

type Slice = { value: number; share: number };
type CoreRow = {
  asset: string; weight: number; price: number; target: number; value: number; drift: number; drift_pct: number;
  action: "buy" | "trim" | "hold"; qty: number; amount: number; note: string;
};
type Trim = { id: number; position_id: number; asset: string; qty: number; price: number; value: number; reason: string; status: string };
type PortfolioState = {
  quote: string; base_currency: string; equity: number; equity_base: number | null;
  fx: { rate: number | null; as_of: string | null; note?: string };
  sleeves: { active: Slice; core: Slice & { target_pct: number } };
  allocation: { by_asset: (Slice & { asset: string })[]; by_class: (Slice & { class: string })[] };
  core: CoreRow[];
  pending: { plans: any[]; trims: Trim[] };
};

const CLASS: Record<string, { label: string; color: string }> = {
  cash: { label: "Cash", color: "var(--t-dim)" },
  bitcoin: { label: "Bitcoin", color: "#f7931a" },
  gold: { label: "Gold", color: "#d4af37" },
  altcoins: { label: "Other coins", color: "var(--brand)" },
  crypto: { label: "Coins", color: "var(--brand)" },
};
const cls = (c: string) => CLASS[c] ?? { label: c, color: "var(--chart-3)" };

function Stat({ label, value, unit, sub, tone, className }: { label: string; value: string; unit?: string; sub?: string; tone?: string; className?: string }) {
  return (
    <div className={cn("bg-panel p-4", className)}>
      <p className="text-xs text-dim">{label}</p>
      <p className={cn("mt-1 font-mono text-2xl tabular-nums", tone)}>{value}{unit && <span className="ml-1.5 text-sm text-dim">{unit}</span>}</p>
      {sub && <p className="text-xs text-dim">{sub}</p>}
    </div>
  );
}

function Drift({ pct, band }: { pct: number; band: number }) {
  const w = Math.min(50, (Math.abs(pct) / Math.max(band * 3, 1)) * 50);
  const out = Math.abs(pct) > band;
  return (
    <div className="relative h-2 w-28 rounded-full bg-sunk" aria-hidden="true">
      <span className="absolute inset-y-0 left-1/2 w-px bg-line" />
      <span className={cn("absolute inset-y-0 rounded-full", out ? (pct < 0 ? "bg-warn" : "bg-brand") : "bg-dim/40")}
        style={pct < 0 ? { right: "50%", width: `${w}%` } : { left: "50%", width: `${w}%` }} />
    </div>
  );
}

export default function Portfolio() {
  const d = useDeskCtx();
  const [p, setP] = useState<PortfolioState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [band, setBand] = useState(5);
  const load = useCallback(() => {
    api<PortfolioState>("/api/portfolio").then((x) => { setP(x); setError(null); }).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { load(); api<any>("/api/settings").then((c) => setBand(c.settings.portfolio.rebalance_band_pct)).catch(() => {}); }, [load]);
  useInterval(load, 30000);

  const act = async (path: string, ok: string) => { if (await d.act(path, "POST", ok)) load(); };

  if (error) return <Page><Box title="Portfolio"><p className="text-sm text-down">Couldn't load the portfolio: {error}</p></Box></Page>;
  if (!p) return <Page><div className="h-40 animate-pulse rounded-xl bg-panel" /></Page>;

  const q = p.quote;
  const coreOn = p.sleeves.core.target_pct > 0;
  const cash = p.allocation.by_class.find((c) => c.class === "cash");
  const waitingPlans = p.pending.plans.filter((x) => x.status === "proposed");
  const waitingTrims = p.pending.trims.filter((x) => x.status === "proposed");
  const corePositions = (d.state?.positions ?? []).filter((x) => x.sleeve === "core");
  const activePositions = (d.state?.positions ?? []).filter((x) => x.sleeve !== "core");

  return (
    <Page>
      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line lg:grid-cols-4">
        <div className="col-span-2 bg-panel p-4 lg:col-span-1">
          <p className="text-xs text-dim">Total value</p>
          <p className="mt-1 font-mono text-3xl tabular-nums">{px(p.equity)} <span className="text-sm text-dim">{q}</span></p>
          <p className="text-xs text-dim">
            {p.equity_base != null
              ? <><b className="font-mono text-fg">{px(p.equity_base)} {p.base_currency}</b> at USD/{p.base_currency} {p.fx.rate?.toFixed(4)}, {p.fx.as_of}</>
              : `${p.base_currency} rate unavailable`}
          </p>
        </div>
        <Stat label="Trading sleeve" value={px(p.sleeves.active.value)} unit={q} sub={`${p.sleeves.active.share.toFixed(0)}% of the account`} />
        <Stat label="Core sleeve" value={coreOn ? px(p.sleeves.core.value) : "Off"} unit={coreOn ? q : undefined}
          sub={coreOn ? `${p.sleeves.core.share.toFixed(0)}% of the account, target ${p.sleeves.core.target_pct}%` : "off"} />
        <Stat label="Cash" value={px(cash?.value ?? 0)} unit={q} sub={`${(cash?.share ?? 0).toFixed(0)}% of the account`} className="col-span-2 lg:col-span-1" />
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 space-y-4">
          <Box title="Allocation">
            <div className="flex h-4 overflow-hidden rounded-full bg-sunk" role="img"
              aria-label={p.allocation.by_class.map((c) => `${cls(c.class).label} ${c.share.toFixed(0)}%`).join(", ")}>
              {p.allocation.by_class.map((c) => <span key={c.class} style={{ width: `${c.share}%`, background: cls(c.class).color }} />)}
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
              {p.allocation.by_class.map((c) => (
                <li key={c.class} className="flex items-center gap-1.5">
                  <span className="size-2.5 rounded-sm" style={{ background: cls(c.class).color }} />
                  {cls(c.class).label} <span className="font-mono text-dim">{c.share.toFixed(1)}%</span>
                </li>
              ))}
            </ul>
            <table className="mt-4 w-full text-[13px]">
              <thead><tr className="text-left text-xs text-dim"><th className="py-1 font-medium">Asset</th><th className="py-1 text-right font-medium">Value</th><th className="py-1 text-right font-medium">Share</th><th className="hidden w-1/3 py-1 sm:table-cell" /></tr></thead>
              <tbody className="divide-y divide-line/60">
                {p.allocation.by_asset.map((a) => (
                  <tr key={a.asset}>
                    <td className="py-2 font-semibold">{a.asset === q ? <>{q} <span className="font-normal text-dim">free cash</span></> : <Link to={`/markets/${a.asset}`} className="inline-block py-1 hover:underline">{a.asset}</Link>}</td>
                    <td className="py-2 text-right font-mono tabular-nums">{px(a.value)}</td>
                    <td className="py-2 text-right font-mono tabular-nums">{a.share.toFixed(1)}%</td>
                    <td className="hidden py-2 pl-4 sm:table-cell"><div className="h-1.5 rounded-full bg-sunk"><div className="h-full rounded-full bg-brand" style={{ width: `${a.share}%` }} /></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Box>

          <Box title={<Term k="core">Core sleeve</Term>} right={coreOn && <span className="text-xs text-dim">rebalances at {band}% drift</span>}>
            {!coreOn ? (
              <div className="space-y-2 text-sm">
                <p>Long-term holdings, e.g. 60% BTC and 40% gold, kept at their target weights while the rest of the account trades.</p>
                <Link to="/settings#portfolio" className="text-brand-strong underline-offset-2 hover:underline">Set the core share and targets in Settings</Link>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-[13px]">
                  <thead>
                    <tr className="text-left text-xs text-dim">
                      <th className="py-1 font-medium">Asset</th><th className="py-1 text-right font-medium">Target weight</th>
                      <th className="py-1 text-right font-medium">Target</th><th className="py-1 text-right font-medium">Now</th>
                      <th className="py-1 pl-4 font-medium"><Term k="drift">Off target</Term></th><th className="py-1 text-right font-medium">Next step</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/60">
                    {p.core.map((r) => (
                      <tr key={r.asset}>
                        <td className="py-2.5 font-semibold">{r.asset}</td>
                        <td className="py-2.5 text-right font-mono">{r.weight}%</td>
                        <td className="py-2.5 text-right font-mono">{px(r.target)}</td>
                        <td className="py-2.5 text-right font-mono">{px(r.value)}</td>
                        <td className="py-2.5 pl-4"><div className="flex items-center gap-2"><Drift pct={r.drift_pct} band={band} /><span className="font-mono text-xs">{pc(r.drift_pct)}</span></div></td>
                        <td className="py-2.5 text-right">
                          {r.action === "buy" && <span>buy {px(r.amount)} {q}</span>}
                          {r.action === "trim" && <span>sell {px(Math.abs(r.drift))} {q}</span>}
                          {r.action === "hold" && <span className="text-dim">{r.note || "on target"}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Box>
        </div>

        <div className="space-y-4">
          <Box title="Pending rebalance" right={(waitingPlans.length + waitingTrims.length) > 0 && <span className="rounded bg-brand px-1.5 text-[11px] font-bold text-brand-fg">{waitingPlans.length + waitingTrims.length}</span>}>
            {!waitingPlans.length && !waitingTrims.length && (
              <p className="text-sm text-dim">{coreOn ? "Nothing to do. The core is within its band, or the next run proposes the gaps." : "The core sleeve is off."}</p>
            )}
            <ul className="space-y-3">
              {waitingPlans.map((x) => (
                <li key={`p${x.id}`} className="rounded-lg border border-line p-3">
                  <p className="text-sm"><b>Buy {x.asset}</b>, {px(x.qty * x.entry)} {q} at market</p>
                  <p className="mt-1 text-xs text-dim">{x.thesis}</p>
                  <p className="mt-1 font-mono text-xs text-dim">stop {px(x.stop)}, target {px(x.take_profit)}</p>
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" onClick={() => act(`/api/plans/${x.id}/approve`, `Buying ${x.asset}`)}>Approve and buy</Button>
                    <Button size="sm" variant="ghost" onClick={() => act(`/api/plans/${x.id}/reject`, "Dropped")}>Drop</Button>
                  </div>
                </li>
              ))}
              {waitingTrims.map((t) => (
                <li key={`t${t.id}`} className="rounded-lg border border-line p-3">
                  <p className="text-sm"><b>Sell {t.asset}</b>, {px(t.qty)} for {px(t.value)} {q}</p>
                  <p className="mt-1 text-xs text-dim">{t.reason}</p>
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" onClick={() => act(`/api/trims/${t.id}/approve`, `Selling ${t.asset}`)}>Approve and sell</Button>
                    <Button size="sm" variant="ghost" onClick={() => act(`/api/trims/${t.id}/reject`, "Dropped")}>Drop</Button>
                  </div>
                </li>
              ))}
            </ul>
          </Box>

          <Box title="Holdings by sleeve" pad={false}>
            {[["Core", corePositions], ["Trading", activePositions]].map(([label, rows]) => (
              <div key={label as string} className="border-b border-line/60 px-4 py-3 last:border-0">
                <p className="mb-1.5 text-xs font-medium text-dim">{label as string}</p>
                {!(rows as any[]).length && <p className="text-[13px] text-dim">None open.</p>}
                <ul className="space-y-1.5 text-[13px]">
                  {(rows as any[]).map((x) => {
                    const now = x.price ?? x.entry_price;
                    const pnl = (now - x.entry_price) * x.qty * (x.side === "long" ? 1 : -1);
                    return (
                      <li key={x.id} className="flex items-center justify-between gap-3">
                        <span><b>{x.asset}</b> <span className="text-dim">{x.horizon}, {px(x.qty)} at {px(x.entry_price)}</span></span>
                        <span className={cn("font-mono tabular-nums", pnl >= 0 ? "text-up" : "text-down")}>{pnl >= 0 ? "+" : "−"}{Math.abs(pnl).toFixed(2)}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </Box>
        </div>
      </div>
    </Page>
  );
}
