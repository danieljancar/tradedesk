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

type Cfg = { path: string; settings: any; read_only: string[]; profiles?: Record<string, Record<string, number>> };

const PROFILE_TEXT: Record<string, string> = {
  conservative: "Half a percent per trade, tight daily and total loss stops, only strong setups.",
  balanced: "One percent per trade, up to four trades at once. The default.",
  aggressive: "Two percent per trade, up to eight trades, lower bar for reward to risk and confidence. Losses come faster too.",
};

function Chips({ items, onChange, placeholder }: { items: string[]; onChange: (v: string[]) => void; placeholder: string }) {
  const [v, setV] = useState("");
  return (
    <div className="flex flex-wrap items-center gap-2">
      {items.map((a) => (
        <span key={a} className="flex items-center gap-1 rounded-full bg-raised py-1 pr-1.5 pl-3 text-sm font-medium">
          {a}
          <button type="button" aria-label={`Remove ${a}`} onClick={() => onChange(items.filter((x) => x !== a))} className="grid size-6 place-items-center rounded-full text-dim hover:bg-sunk hover:text-down"><X className="size-3.5" /></button>
        </span>
      ))}
      <form className="flex gap-1.5" onSubmit={(e) => { e.preventDefault(); const c = v.trim().toUpperCase(); if (c && !items.includes(c)) onChange([...items, c]); setV(""); }}>
        <Input value={v} onChange={(e) => setV(e.target.value)} placeholder={placeholder} className="h-8 w-32 uppercase" />
        <Button size="sm" type="submit" variant="outline" className="h-8">Add</Button>
      </form>
    </div>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span><span className="text-sm font-medium">{label}</span><span className="block text-xs text-dim">{hint}</span></span>
      <Switch checked={checked} onCheckedChange={onChange} />
    </label>
  );
}

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
  const risk = draft.risk, exe = draft.execution, uni = draft.universe, port = draft.portfolio, ntf = draft.notify;
  const profiles = cfg.profiles ?? {};
  const setUni = (k: string, v: any) => setDraft({ ...draft, universe: { ...uni, [k]: v } });
  const setPort = (k: string, v: any) => setDraft({ ...draft, portfolio: { ...port, [k]: v } });
  const setNtf = (k: string, v: any) => setDraft({ ...draft, notify: { ...ntf, [k]: v } });
  const pickProfile = (name: string | null) => setDraft({ ...draft, risk: { ...risk, ...(name ? profiles[name] : {}), profile: name } });
  const tweaked = risk.profile && profiles[risk.profile] ? Object.entries(profiles[risk.profile]).filter(([k, v]) => risk[k] !== v).map(([k]) => k) : [];
  const targets: [string, number][] = Object.entries(port.core_targets ?? {});
  const weightSum = targets.reduce((a, [, w]) => a + Number(w || 0), 0);
  const setTargets = (rows: [string, number][]) => setPort("core_targets", Object.fromEntries(rows.filter(([a]) => a)));
  const tg = d.state?.telegram;
  const setRisk = (k: string, v: any) => setDraft({ ...draft, risk: { ...risk, [k]: v } });
  const setExe = (k: string, v: any) => setDraft({ ...draft, execution: { ...exe, [k]: v } });
  const dirty = JSON.stringify(draft) !== JSON.stringify(s);
  const eq = d.state?.equity.at(-1)?.value ?? s.paper_equity;
  const lossAtStop = risk.principal ? Math.min(eq, risk.principal) * risk.risk_per_trade_pct / 100 + Math.max(0, eq - risk.principal) * risk.profit_risk_pct / 100 : eq * risk.risk_per_trade_pct / 100;

  const save = async () => {
    setSaving(true);
    try {
      const body: any = { watchlist: draft.watchlist, risk: draft.risk, execution: draft.execution, hold_days: draft.hold_days, universe: draft.universe, portfolio: draft.portfolio, notify: draft.notify };
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
                <button type="button" aria-label={`Remove ${a}`} onClick={() => setDraft({ ...draft, watchlist: draft.watchlist.filter((x: string) => x !== a) })} className="grid size-6 place-items-center rounded-full text-dim hover:bg-sunk hover:text-down"><X className="size-3.5" /></button>
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

      <Box title="Market scan">
        <div className="space-y-4">
          <Toggle label="Scan the whole market every run" hint="Off: the desk only looks at the watchlist above." checked={uni.enabled} onChange={(v) => setUni("enabled", v)} />
          <Field label="Coins the scan adds" term="scan" hint="The strongest movers by 7-day change against Bitcoin, volume surge and typical move size."><Num value={uni.top} onChange={(v) => setUni("top", v ?? 0)} step={1} /></Field>
          <Field label="Minimum 24h volume" hint="Thin coins are skipped. In millions of USDT."><Num value={uni.min_quote_volume / 1e6} onChange={(v) => setUni("min_quote_volume", (v ?? 0) * 1e6)} step={5} suffix="M" /></Field>
          <Field label="Most assets per run" hint="Watchlist, gold, core holdings and scan picks together. More assets cost more tokens per run."><Num value={uni.max_assets} onChange={(v) => setUni("max_assets", v ?? 1)} step={1} /></Field>
          <Toggle label="Include gold" hint="Adds PAXG. One token is one troy ounce of gold, traded against USDT around the clock." checked={uni.include_gold} onChange={(v) => setUni("include_gold", v)} />
          <div><p className="mb-2 text-sm font-medium">Always look at</p><Chips items={uni.always} onChange={(v) => setUni("always", v)} placeholder="e.g. BNB" /></div>
          <div><p className="mb-2 text-sm font-medium">Never pick</p><Chips items={uni.exclude} onChange={(v) => setUni("exclude", v)} placeholder="e.g. PEPE" /></div>
        </div>
      </Box>

      <Box title="Risk profile" right={tweaked.length > 0 && <span className="text-xs text-dim">{risk.profile} with your own {tweaked.length === 1 ? "change" : "changes"} to {tweaked.length} {tweaked.length === 1 ? "limit" : "limits"}</span>}>
        <div className="grid gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Risk profile">
          {[null, "conservative", "balanced", "aggressive"].map((name) => (
            <button key={name ?? "custom"} type="button" role="radio" aria-checked={risk.profile === name} onClick={() => pickProfile(name)}
              className={cn("min-h-11 rounded-lg border px-3 py-2.5 text-left transition-colors", risk.profile === name ? "border-brand bg-brand-soft" : "border-line hover:bg-raised")}>
              <span className="block text-sm font-semibold capitalize">{name ?? "Custom"}</span>
              <span className="mt-0.5 block text-xs leading-snug text-dim">{name ? PROFILE_TEXT[name] : "Every limit set by hand below."}</span>
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-dim">A profile fills in the limits below. Change any of them and your value wins. The total loss stop and the exchange stop on every trade stay on in every profile.</p>
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

      <section id="portfolio" className="scroll-mt-4">
        <Box title={<Term k="core">Core sleeve</Term>} right={port.core_pct > 0 && targets.length > 0 && <span className={cn("text-xs", Math.abs(weightSum - 100) > 0.01 ? "text-down" : "text-dim")}>weights add up to {weightSum}%</span>}>
          <div className="space-y-4">
            <Field label="Share of the account held long term" hint="0 turns it off. The trading sleeve sizes its trades on the rest."><Num value={port.core_pct} onChange={(v) => setPort("core_pct", v ?? 0)} step={5} suffix="%" /></Field>
            <div>
              <p className="text-sm font-medium">Targets</p>
              <p className="mb-2 text-xs text-dim">Weights inside the core, adding up to 100. For example BTC 60 and PAXG 40.</p>
              <ul className="space-y-2">
                {targets.map(([a, w], i) => (
                  <li key={i} className="flex items-center gap-2">
                    <Input value={a} onChange={(e) => setTargets(targets.map((r, j) => (j === i ? [e.target.value.toUpperCase(), r[1]] : r)))} className="h-9 w-28 uppercase" aria-label="Asset" />
                    <div className="w-32"><Num value={w} onChange={(v) => setTargets(targets.map((r, j) => (j === i ? [r[0], v ?? 0] : r)))} step={5} suffix="%" /></div>
                    <button type="button" aria-label={`Remove ${a}`} onClick={() => setTargets(targets.filter((_, j) => j !== i))} className="rounded p-1.5 text-dim hover:text-down"><X className="size-4" /></button>
                  </li>
                ))}
              </ul>
              <Button size="sm" variant="outline" className="mt-2 h-8" onClick={() => setTargets([...targets, ["", 0]])}>Add asset</Button>
            </div>
            <Field label="Rebalance band" term="drift" hint="Only rebalance an asset once it is this far off its own target."><Num value={port.rebalance_band_pct} onChange={(v) => setPort("rebalance_band_pct", v ?? 5)} step={1} suffix="%" /></Field>
            <Field label="Core stop" hint="Wide stop on the exchange under every core buy, for a crash, not daily swings."><Num value={port.core_stop_pct} onChange={(v) => setPort("core_stop_pct", v ?? 35)} step={5} suffix="%" /></Field>
          </div>
        </Box>
      </section>

      <Box title="Telegram" right={<span className={cn("text-xs", tg?.configured ? "text-up" : "text-dim")}>{tg?.configured ? "bot token and chat id found" : "no bot token in .env yet"}</span>}>
        <div className="space-y-4">
          <Toggle label="Send messages to Telegram" hint="Plans with Approve and Drop buttons, fills, stops and targets, errors, run summaries. Takes effect after restarting the dashboard and the bot." checked={ntf.telegram} onChange={(v) => setNtf("telegram", v)} />
          <div>
            <p className="mb-2 text-sm font-medium">What to send</p>
            <div className="flex flex-wrap gap-2">
              {([["proposed", "New plans"], ["fill", "Fills"], ["exit", "Stops and targets"], ["error", "Errors"], ["run", "Run summaries"], ["kill", "Kill switch"]] as const).map(([k, label]) => {
                const on = ntf.events.includes(k);
                return (
                  <button key={k} type="button" aria-pressed={on} onClick={() => setNtf("events", on ? ntf.events.filter((x: string) => x !== k) : [...ntf.events, k])}
                    className={cn("min-h-9 rounded-full border px-3 text-sm", on ? "border-brand bg-brand-soft text-brand-strong" : "border-line text-dim hover:text-fg")}>{label}</button>
                );
              })}
            </div>
          </div>
          <Field label="Quiet hours" hint='Local time, e.g. "23-07". Then only errors and stop-outs come through.'>
            <Input value={ntf.quiet_hours} onChange={(e) => setNtf("quiet_hours", e.target.value)} placeholder="off" className="h-9 text-right font-mono" />
          </Field>
          {!tg?.configured && <p className="rounded-md bg-sunk px-3 py-2 text-xs text-dim">Create a bot with BotFather in Telegram, put TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env, then run <code className="font-mono">uv run desk bot</code>. The README has the steps.</p>}
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
