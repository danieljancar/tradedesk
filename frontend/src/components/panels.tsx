import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Area, AreaChart, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Prose } from "@/components/prose";
import { Term } from "@/components/term";
import { said } from "@/components/floor";
import { ABOUT, CAST, portrait } from "@/lib/cast";
import { GLOSSARY, planStory, px } from "@/lib/learn";
import { api, type DeskEvent, type DeskState, type Plan } from "@/lib/api";
import { cn } from "@/lib/utils";

const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const money = (n: number) => `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(2)}`;

export function Avatar({ id, size = 40, mood = "awake", className }: { id: string; size?: number; mood?: string; className?: string }) {
  return <span className={cn("inline-grid shrink-0 place-items-center", className)} dangerouslySetInnerHTML={{ __html: portrait(id, { size, mood }) }} />;
}

// ---------- today's call ----------
export function Call({ events }: { events: DeskEvent[] }) {
  const pm = [...events].reverse().find((e) => e.actor === "pm" && e.kind !== "start" && e.html);
  const risk = [...events].reverse().find((e) => e.actor === "risk" && e.kind !== "start");
  const verdict = pm ? ((pm.body?.match(/^#\s*(.+)$/m)?.[1] ?? pm.title).split(":").pop() || "").trim() : "";
  return (
    <Card className="call-card gap-4">
      <CardHeader className="flex flex-row items-center gap-4">
        <Avatar id="pm" size={64} mood={pm ? "done" : "idle"} />
        <div>
          <CardDescription className="eyebrow">Today's call</CardDescription>
          <CardTitle className="font-heading text-3xl capitalize">{pm ? verdict : "Not decided yet"}</CardTitle>
          {pm && <p className="text-xs text-muted-foreground">Portfolio manager at {clock(pm.ts)}{risk ? ` · Risk engine: ${risk.title}` : ""}</p>}
        </div>
      </CardHeader>
      {pm && (
        <CardContent>
          <Prose html={pm.html} strip="h1" className="text-[15px]" />
        </CardContent>
      )}
    </Card>
  );
}

// ---------- plans ----------
function Ladder({ p }: { p: Plan }) {
  const pts = [p.stop, p.entry, p.take_profit];
  const lo = Math.min(...pts), hi = Math.max(...pts);
  const at = (v: number) => ((v - lo) / (hi - lo || 1)) * 100;
  const seg = (a: number, b: number) => ({ left: `${Math.min(at(a), at(b))}%`, width: `${Math.abs(at(a) - at(b))}%` });
  return (
    <div className="relative mx-2 mt-10 mb-12 h-2.5 rounded-full bg-muted" role="img" aria-label={`Stop ${px(p.stop)}, entry ${px(p.entry)}, target ${px(p.take_profit)}`}>
      <span className="absolute inset-y-0 rounded-full bg-down/70" style={seg(p.stop, p.entry)} />
      <span className="absolute inset-y-0 rounded-full bg-up/70" style={seg(p.entry, p.take_profit)} />
      {([["stop", p.stop, "stop"], ["entry", p.entry, "entry"], ["target", p.take_profit, "target"]] as const).map(([label, v, key]) => (
        <span key={label} className="absolute top-1/2 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center" style={{ left: `${at(v)}%` }}>
          <b className="absolute bottom-5 font-mono text-xs tabular-nums whitespace-nowrap">{px(v)}</b>
          <span className="size-3.5 rounded-full border-2 border-background bg-foreground shadow" />
          <span className="absolute top-5 text-xs"><Term k={key}>{label}</Term></span>
        </span>
      ))}
    </div>
  );
}

export function Plans({ state, refresh }: { state: DeskState | null; refresh: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const act = async (path: string, id: string, ok: string) => {
    setBusy(id);
    try { await api(path, "POST"); toast.success(ok); } catch (e: any) { toast.error(e.message); }
    setBusy(null);
    refresh();
  };
  const plans = state?.plans ?? [];
  if (!plans.length) {
    return (
      <Card className="flex-row items-center gap-5 px-6 py-5">
        <Avatar id="pm" size={64} mood="idle" />
        <div>
          <p className="font-medium">No trade ideas right now.</p>
        </div>
      </Card>
    );
  }
  return (
    <div className="grid gap-4">
      {plans.map((p) => {
        const waiting = p.status === "proposed";
        return (
          <Card key={p.id} className={cn("gap-3", waiting && "ring-2 ring-primary/40")}>
            <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={cn("uppercase", p.side === "long" ? "bg-up text-white" : "bg-down text-white")}>{p.side}</Badge>
                <CardTitle className="font-heading text-2xl">{p.asset}{p.venue === "futures" && <span className="ml-1.5 rounded bg-warn/12 px-1 py-px text-xs align-middle font-medium text-warn">futures{p.leverage > 1 ? ` ${p.leverage}x` : ""}</span>}</CardTitle>
                <Badge variant="outline">{p.horizon} term</Badge>
                <Badge variant="outline"><Term k="confidence" /> {p.confidence}</Badge>
                {p.reward_risk && <Badge variant="outline"><Term k="rr">R/R</Term> {p.reward_risk}</Badge>}
              </div>
              <Badge variant={waiting ? "default" : "secondary"} className="capitalize">{waiting ? "Waiting for you" : p.status}</Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-[15px] leading-relaxed">{planStory(p, state?.quote)}</p>
              <Ladder p={p} />
              <p className="text-sm text-muted-foreground"><b className="text-foreground">Why: </b>{p.thesis}</p>
              {p.status === "rejected" && p.reasons && <p className="rounded-md bg-down/10 px-3 py-2 text-sm text-down"><b>Risk engine said no: </b>{p.reasons}</p>}
              {waiting && (
                <div className="flex gap-2 pt-1">
                  <Button disabled={busy === p.id} onClick={() => act(`/api/plans/${p.id}/approve`, p.id, "Sent with its stop on the exchange")}>Approve and send</Button>
                  <Button variant="ghost" disabled={busy === p.id} onClick={() => act(`/api/plans/${p.id}/reject`, p.id, "Dropped")}>Drop</Button>
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

// ---------- conversation ----------
export function Talk({ events, onPick }: { events: DeskEvent[]; onPick: (id: string) => void }) {
  const items = events.filter((e) => CAST[e.actor] && (e.kind !== "start" || ["technical", "news", "bull", "bear", "pm"].includes(e.actor)));
  if (!items.length) return <p className="text-sm text-muted-foreground">Nothing said in this run yet.</p>;
  return (
    <ol className="relative space-y-3 before:absolute before:top-2 before:bottom-2 before:left-5 before:w-px before:bg-border">
      <AnimatePresence initial={false}>
        {items.map((e) => {
          const c = CAST[e.actor];
          const mood = e.kind === "start" ? "working" : e.kind === "reject" || e.kind === "error" ? "alert" : "done";
          return (
            <motion.li key={e.id} layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="relative flex gap-3">
              <button type="button" onClick={() => onPick(e.actor)} className="relative z-10 rounded-full bg-background" aria-label={`Open ${c.name}`}>
                <Avatar id={e.actor} size={40} mood={mood} />
              </button>
              <div className={cn("min-w-0 flex-1 rounded-xl border bg-card px-4 py-3", e.kind === "start" && "border-dashed bg-transparent")}>
                <header className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <b>{c.name}</b><span className="text-muted-foreground">{c.role}</span>
                  <time className="ml-auto text-xs text-muted-foreground tabular-nums" dateTime={e.ts}>{clock(e.ts)}</time>
                </header>
                <p className={cn("mt-0.5", e.kind === "start" ? "text-sm text-muted-foreground italic" : "font-medium")}>{said(e)}</p>
                {e.html && (
                  <details className="group mt-2">
                    <summary className="cursor-pointer text-sm font-medium text-primary underline-offset-4 hover:underline">Read what they wrote</summary>
                    <Prose html={e.html} className="mt-2 text-sm" />
                  </details>
                )}
              </div>
            </motion.li>
          );
        })}
      </AnimatePresence>
    </ol>
  );
}

// ---------- account ----------
export function Account({ state, refresh }: { state: DeskState | null; refresh: () => void }) {
  if (!state) return null;
  const vals = state.equity;
  const L = state.limits;
  const eq = vals.at(-1)?.value;
  const base = state.invested ?? vals[0]?.value;
  const diff = eq != null && base != null ? eq - base : 0;
  const data = vals.map((v) => ({ t: new Date(v.ts).toLocaleDateString([], { month: "short", day: "numeric" }), v: v.value }));
  const closePos = async (id: string, asset: string) => {
    if (!confirm(`Close ${asset} at market now?`)) return;
    try { await api(`/api/positions/${id}/close`, "POST"); toast.success("Closed"); } catch (e: any) { toast.error(e.message); }
    refresh();
  };
  return (
    <div className="space-y-4">
      <Card className="gap-2">
        <CardHeader>
          <CardDescription className="eyebrow"><Term k="equity">Account</Term></CardDescription>
          <CardTitle className="font-heading text-4xl tabular-nums">
            {eq == null ? "…" : eq.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            <span className="ml-1.5 text-base font-normal text-muted-foreground">{state.quote}</span>
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            {state.mode === "paper" ? <><Term k="paper">Pretend money</Term> on real prices · </> : null}
            <span className={diff >= 0 ? "text-up" : "text-down"}>{money(diff)}</span> profit on {(base ?? 0).toFixed(2)} put in
          </p>
        </CardHeader>
        <CardContent className="px-2">
          <ChartContainer config={{ v: { label: "Equity", color: "var(--up)" } }} className="h-28 w-full">
            <AreaChart data={data.length > 1 ? data : [...data, ...data]} margin={{ left: 0, right: 0, top: 6, bottom: 0 }}>
              <defs>
                <linearGradient id="eqfill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-v)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--color-v)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="t" hide />
              <YAxis domain={["dataMin - 5", "dataMax + 5"]} hide />
              <ChartTooltip content={<ChartTooltipContent hideIndicator />} />
              <Area dataKey="v" type="monotone" stroke="var(--color-v)" strokeWidth={2} fill="url(#eqfill)" />
            </AreaChart>
          </ChartContainer>
        </CardContent>
      </Card>

      <Card className="gap-3">
        <CardHeader><CardTitle className="text-base">Open trades</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {!state.positions.length && <p className="text-sm text-muted-foreground">No open positions.</p>}
          {state.positions.map((p) => {
            const sign = p.side === "long" ? 1 : -1;
            const pnl = p.price == null ? 0 : (p.price - p.entry_price) * p.qty * sign;
            const lo = Math.min(p.stop, p.take_profit), hi = Math.max(p.stop, p.take_profit);
            const raw = p.price == null ? 0.5 : Math.max(0, Math.min(1, (p.price - lo) / (hi - lo)));
            const k = sign > 0 ? raw : 1 - raw;
            return (
              <div key={p.id} className="space-y-2 rounded-lg border p-3">
                <div className="flex items-center justify-between"><b>{p.asset} {p.side}</b><b className={pnl >= 0 ? "text-up" : "text-down"}>{money(pnl)}</b></div>
                <p className="text-xs text-muted-foreground">{px(p.qty)} at {px(p.entry_price)} · now {px(p.price)}</p>
                <div className="relative h-2 rounded-full bg-gradient-to-r from-down/60 to-up/60">
                  <span className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground" style={{ left: `${k * 100}%` }} />
                </div>
                <div className="flex justify-between text-xs text-muted-foreground"><span><Term k="stop">stop</Term> {px(p.stop)}</span><span>{px(p.take_profit)} <Term k="target">target</Term></span></div>
                <Button size="sm" variant="outline" onClick={() => closePos(p.id, p.asset)}>Close now</Button>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card className="gap-3">
        <CardHeader><CardTitle className="text-base">Closed trades</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {!state.closed.length && <p className="text-sm text-muted-foreground">No finished trades yet.</p>}
          {state.closed.map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-2 text-sm">
              <span><b>{p.asset}</b> {p.side} · {String(p.closed_at).slice(5, 10)}</span>
              <span className="truncate text-xs text-muted-foreground">{p.exit_reason}</span>
              <b className={p.pnl >= 0 ? "text-up" : "text-down"}>{money(p.pnl)}</b>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="gap-3 bg-muted/40">
        <CardHeader><CardTitle className="text-base">House rules</CardTitle></CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm">
            <li>Loss at the stop: <b>{L?.risk_per_trade_pct ?? "–"}%</b> of the account (<Term k="risk">risk per trade</Term>){(L?.confident_risk_x ?? 1) > 1 ? <>, up to <b>{(L!.risk_per_trade_pct * L!.confident_risk_x).toFixed(1)}%</b> at full conviction</> : null}.</li>
            <li>Minimum <Term k="rr">R/R</Term>: <b>{L?.min_reward_risk ?? "–"}×</b>.</li>
            <li>Every <Term k="stop">stop</Term> is on the exchange from the first fill.</li>
            <li>No new trades after <b>{L?.daily_loss_limit_pct ?? "–"}%</b> down in a day or <b>{L?.max_drawdown_pct ?? "–"}%</b> from the peak (<Term k="drawdown">drawdown</Term>).</li>
            <li>{state.auto_execute ? "Passed plans go out without approval." : "Every order needs your approval."}</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------- agent sheet ----------
export function AgentSheet({ id, events, onClose }: { id: string | null; events: DeskEvent[]; onClose: () => void }) {
  const c = id ? CAST[id] : null;
  const items = id ? events.filter((e) => e.actor === id && e.kind !== "start") : [];
  return (
    <Sheet open={!!id} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="flex w-full flex-col gap-0 overflow-hidden sm:max-w-xl">
        {c && id && (
          <>
            <SheetHeader className="flex-row items-center gap-4 border-b">
              <Avatar id={id} size={84} mood="awake" className="agent-wave" />
              <div>
                <SheetTitle className="font-heading text-2xl">{c.name}</SheetTitle>
                <SheetDescription>{c.role}</SheetDescription>
              </div>
            </SheetHeader>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <div className="space-y-4 p-4">
                <p className="rounded-lg bg-muted/60 p-3 text-sm leading-relaxed">{ABOUT[id]}</p>
                {!items.length && <p className="text-sm text-muted-foreground">No output this run.</p>}
                {items.map((e) => (
                  <article key={e.id} className="rounded-xl border p-4">
                    <header className="mb-2 flex items-baseline justify-between gap-2"><b>{e.title}</b><time className="text-xs text-muted-foreground">{clock(e.ts)}</time></header>
                    {e.html && <Prose html={e.html} className="text-sm" />}
                  </article>
                ))}
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

// ---------- glossary ----------
export function Glossary({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [q, setQ] = useState("");
  const items = useMemo(() => Object.values(GLOSSARY).sort((a, b) => a.term.localeCompare(b.term)), []);
  const shown = items.filter((g) => !q || `${g.term} ${g.short} ${g.long ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85dvh] flex-col overflow-hidden sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-heading text-2xl">Learn the words</DialogTitle>
          <DialogDescription>Terms the desk uses.</DialogDescription>
        </DialogHeader>
        <Input type="search" placeholder="Search, e.g. RSI or stop" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search the glossary" />
        <div className="-mr-2 min-h-0 flex-1 overflow-y-auto overscroll-contain pr-2">
          <dl className="divide-y">
            {shown.map((g) => (
              <div key={g.term} className="space-y-1 py-3">
                <dt className="font-medium">{g.term}</dt>
                <dd className="text-sm">{g.short}</dd>
                {g.long && <dd className="text-sm text-muted-foreground">{g.long}</dd>}
              </div>
            ))}
            {!shown.length && <p className="py-6 text-sm text-muted-foreground">No matches.</p>}
          </dl>
        </div>
      </DialogContent>
    </Dialog>
  );
}
