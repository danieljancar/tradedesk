import { useEffect, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Box, Page } from "@/components/shell";
import { Term } from "@/components/term";
import { api } from "@/lib/api";
import { send, useDeskCtx } from "@/lib/desk-context";
import { cn } from "@/lib/utils";

type Cfg = { path: string; settings: any; read_only: string[] };

function Field({ label, hint, term, children }: { label: string; hint?: string; term?: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 sm:grid-cols-[minmax(0,1fr)_160px] sm:items-center sm:gap-4">
      <span>
        <span className="text-sm font-medium">{term ? <Term k={term}>{label}</Term> : label}</span>
        {hint && <span className="block text-xs leading-snug text-dim">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

function Num({ value, onChange, step = 0.5, suffix }: { value: number | null | undefined; onChange: (v: number | null) => void; step?: number; suffix?: string }) {
  return (
    <div className="relative">
      <Input type="number" step={step} value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} className="h-9 pr-9 text-right font-mono" />
      {suffix && <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-dim">{suffix}</span>}
    </div>
  );
}

export default function Settings() {
  const d = useDeskCtx();
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [draft, setDraft] = useState<any>(null);
  const [coin, setCoin] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { api<Cfg>("/api/settings").then((c) => { setCfg(c); setDraft(structuredClone(c.settings)); }).catch((e) => toast.error(e.message)); }, []);
  if (!cfg || !draft) return <Page><p className="text-sm text-dim">Loading settings…</p></Page>;

  const s = cfg.settings;
  const risk = draft.risk, exe = draft.execution;
  const setRisk = (k: string, v: any) => setDraft({ ...draft, risk: { ...risk, [k]: v } });
  const setExe = (k: string, v: any) => setDraft({ ...draft, execution: { ...exe, [k]: v } });
  const dirty = JSON.stringify(draft) !== JSON.stringify(s);
  const eq = d.state?.equity.at(-1)?.value ?? s.paper_equity;
  const lossAtStop = risk.principal ? Math.min(eq, risk.principal) * risk.risk_per_trade_pct / 100 + Math.max(0, eq - risk.principal) * risk.profit_risk_pct / 100 : eq * risk.risk_per_trade_pct / 100;

  const save = async () => {
    setSaving(true);
    try {
      const body: any = { watchlist: draft.watchlist, risk: draft.risk, execution: draft.execution, hold_days: draft.hold_days };
      if (s.mode === "paper") body.paper_equity = draft.paper_equity;
      const c = await send("/api/settings", "PUT", body);
      setCfg(c); setDraft(structuredClone(c.settings));
      toast.success("Saved. The next desk run uses it.");
      d.refresh();
    } catch (e: any) { toast.error(e.message); }
    setSaving(false);
  };

  return (
    <Page className="max-w-5xl">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-panel px-4 py-3">
        <div className="text-sm">
          <span className={cn("mr-2 rounded px-1.5 py-0.5 text-[11px] font-bold uppercase", s.mode === "live" ? "bg-down/15 text-down" : "bg-brand-soft text-brand-strong")}>{s.mode}</span>
          <span className="font-medium">{s.market === "futures" ? "Futures, long and short" : "Spot, long only"}</span>
          <span className="ml-2 text-xs text-dim">from {cfg.path.split("/").slice(-2).join("/")}</span>
        </div>
        <p className="text-xs text-dim sm:ml-auto">Mode and market only change in the config file by hand, so going live is always deliberate.</p>
      </div>

      <Box title="Markets">
        <div className="space-y-4">
          <Field label="Watchlist" hint="Coins the desk analyses and may trade. Quoted in USDT.">
            <span />
          </Field>
          <div className="flex flex-wrap items-center gap-2">
            {draft.watchlist.map((a: string) => (
              <span key={a} className="flex items-center gap-1 rounded-full bg-raised py-1 pr-1.5 pl-3 text-sm font-medium">
                {a}
                <button type="button" aria-label={`Remove ${a}`} onClick={() => setDraft({ ...draft, watchlist: draft.watchlist.filter((x: string) => x !== a) })} className="rounded-full p-0.5 text-dim hover:bg-sunk hover:text-down"><X className="size-3.5" /></button>
              </span>
            ))}
            <form className="flex gap-1.5" onSubmit={(e) => { e.preventDefault(); const c = coin.trim().toUpperCase(); if (c && !draft.watchlist.includes(c)) setDraft({ ...draft, watchlist: [...draft.watchlist, c] }); setCoin(""); }}>
              <Input value={coin} onChange={(e) => setCoin(e.target.value)} placeholder="Add, e.g. BNB" className="h-8 w-32 uppercase" />
              <Button size="sm" type="submit" variant="outline" className="h-8">Add</Button>
            </form>
          </div>
          {s.mode === "paper" && (
            <Field label="Paper starting balance" hint="Pretend money the simulation starts with.">
              <Num value={draft.paper_equity} onChange={(v) => setDraft({ ...draft, paper_equity: v ?? 0 })} step={10} suffix="USDT" />
            </Field>
          )}
        </div>
      </Box>

      <Box title="Risk per trade" right={<span className="text-xs text-dim">Right now a stopped-out trade costs about <b className="font-mono text-fg">{lossAtStop.toFixed(2)} USDT</b></span>}>
        <div className="space-y-4">
          <Field label="Risk on your money" term="risk" hint="Share of the account lost if a stop is hit. Max 5%."><Num value={risk.risk_per_trade_pct} onChange={(v) => setRisk("risk_per_trade_pct", v)} suffix="%" /></Field>
          <Field label="Principal" hint="The money you put in. Leave empty to size everything from the current balance."><Num value={risk.principal} onChange={(v) => setRisk("principal", v)} step={10} suffix="USDT" /></Field>
          <Field label="Risk on profits" hint="House money: profits above the principal can be risked at this higher rate."><Num value={risk.profit_risk_pct} onChange={(v) => setRisk("profit_risk_pct", v)} suffix="%" /></Field>
          <Field label="Protected floor" hint="Share of the principal that open stops may never put at risk, even if every stop hits at once."><Num value={risk.floor_pct} onChange={(v) => setRisk("floor_pct", v)} step={5} suffix="%" /></Field>
        </div>
      </Box>

      <Box title="Limits">
        <div className="grid gap-4 lg:grid-cols-2 lg:gap-x-10">
          <Field label="Open trades at once" hint="Positions plus waiting entries."><Num value={risk.max_open_positions} onChange={(v) => setRisk("max_open_positions", v)} step={1} /></Field>
          <Field label="All open stops together" hint="Total loss if everything stops out."><Num value={risk.max_total_risk_pct} onChange={(v) => setRisk("max_total_risk_pct", v)} suffix="%" /></Field>
          <Field label="Reward to risk, minimum" term="rr"><Num value={risk.min_reward_risk} onChange={(v) => setRisk("min_reward_risk", v)} step={0.1} suffix="×" /></Field>
          <Field label="Confidence, minimum" term="confidence"><Num value={risk.min_confidence} onChange={(v) => setRisk("min_confidence", v)} step={5} /></Field>
          <Field label="Leverage cap" term="futures" hint="Futures only. The desk uses as little as each trade needs."><Num value={risk.max_leverage} onChange={(v) => setRisk("max_leverage", v)} step={1} suffix="×" /></Field>
          <Field label="Position size cap" hint="Share of the account per trade, before leverage."><Num value={risk.max_position_pct} onChange={(v) => setRisk("max_position_pct", v)} step={5} suffix="%" /></Field>
          <Field label="Daily loss stop" hint="No new trades for the rest of the UTC day."><Num value={risk.daily_loss_limit_pct} onChange={(v) => setRisk("daily_loss_limit_pct", v)} suffix="%" /></Field>
          <Field label="Total loss stop" term="drawdown" hint="No new trades until the account recovers."><Num value={risk.max_drawdown_pct} onChange={(v) => setRisk("max_drawdown_pct", v)} step={5} suffix="%" /></Field>
          <Field label="Closest stop" term="atr" hint="Stops nearer than this many ATRs are refused as noise."><Num value={risk.min_stop_atr} onChange={(v) => setRisk("min_stop_atr", v)} step={0.1} suffix="ATR" /></Field>
          <Field label="Furthest limit entry" hint="Limit orders further from price than this are refused."><Num value={risk.max_entry_distance_pct} onChange={(v) => setRisk("max_entry_distance_pct", v)} suffix="%" /></Field>
        </div>
      </Box>

      <Box title="Execution">
        <div className="space-y-4">
          <label className="flex items-center justify-between gap-4">
            <span><span className="text-sm font-medium">Trade without asking</span><span className="block text-xs text-dim">On: every plan that passes the risk rules is sent right away. Off: plans wait for your approval on the Trades page.</span></span>
            <Switch checked={exe.auto_execute} onCheckedChange={(v) => setExe("auto_execute", v)} />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span><span className="text-sm font-medium">Close trades that outlive their horizon</span><span className="block text-xs text-dim">Short 3 days, mid 21, long 120.</span></span>
            <Switch checked={exe.close_expired} onCheckedChange={(v) => setExe("close_expired", v)} />
          </label>
          <Field label="Cancel unfilled entries after" hint="Limit orders that never fill."><Num value={exe.entry_ttl_hours} onChange={(v) => setExe("entry_ttl_hours", v)} step={1} suffix="h" /></Field>
        </div>
      </Box>

      <div className="sticky bottom-16 z-10 flex items-center gap-3 rounded-xl border border-line bg-panel/95 px-4 py-3 backdrop-blur md:bottom-3">
        <p className="text-sm text-dim">{dirty ? "Unsaved changes." : "Everything saved."}</p>
        <Button variant="ghost" className="ml-auto" disabled={!dirty} onClick={() => setDraft(structuredClone(s))}>Discard</Button>
        <Button disabled={!dirty || saving} onClick={save}>{saving ? "Saving…" : "Save settings"}</Button>
      </div>
    </Page>
  );
}
