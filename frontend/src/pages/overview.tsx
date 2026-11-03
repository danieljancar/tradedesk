import { useState } from "react";
import { Link } from "react-router";
import { ArrowRight, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Box, Page } from "@/components/shell";
import { Compare, DriverCard, FearGreed, big, type Driver } from "@/components/overview";
import { Avatar } from "@/components/panels";
import { Prose } from "@/components/prose";
import { useDeskCtx } from "@/lib/desk-context";
import { pc } from "@/lib/learn";
import { cn } from "@/lib/utils";

const ago = (s: number) => { const m = Math.round((Date.now() / 1000 - s) / 60); return m < 60 ? `${m}m` : `${Math.round(m / 60)}h`; };

export default function Overview() {
  const d = useDeskCtx();
  const m = d.macro;
  const [note, setNote] = useState("");
  const latest = d.runs[0];
  const live = latest?.status === "running";
  const pm = [...d.events].reverse().find((e) => e.actor === "pm" && e.kind !== "start" && e.html);
  const waiting = d.state?.plans.filter((p) => p.status === "proposed") ?? [];
  const r = m?.regime;
  const tone = r?.label === "Risk-on" ? "text-up" : r?.label === "Risk-off" ? "text-down" : "text-warn";
  const drivers: Driver[] = m?.drivers ?? [];
  const c = m?.crypto ?? {};

  return (
    <Page>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-4">
          <section className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line lg:grid-cols-[1.5fr_repeat(4,minmax(0,1fr))]">
            <div className="col-span-2 bg-panel p-4 lg:col-span-1">
              <p className="text-xs font-medium text-dim">Macro backdrop for crypto</p>
              <p className={cn("font-heading text-3xl font-semibold", tone)}>{r?.label ?? "Loading"}</p>
              {r && (
                <>
                  <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-sunk">
                    <span className="bg-up" style={{ width: `${(r.tailwinds / r.total) * 100}%` }} />
                    <span className="bg-dim/30" style={{ width: `${((r.total - r.tailwinds - r.headwinds) / r.total) * 100}%` }} />
                    <span className="bg-down" style={{ width: `${(r.headwinds / r.total) * 100}%` }} />
                  </div>
                  <p className="mt-2 text-[13px] leading-snug text-dim">
                    {r.tailwinds} of {r.total} drivers help crypto right now, {r.headwinds} work against it. Hover or tap a card to see why.
                  </p>
                </>
              )}
            </div>
            {[
              ["Crypto market cap", big(c.market_cap), c.change_24h],
              ["24h volume", big(c.volume), null],
              ["Bitcoin dominance", c.btc_dominance != null ? `${c.btc_dominance.toFixed(1)}%` : "–", null],
              ["Fear & Greed", m?.fear_greed?.at(-1)?.v ?? "–", null],
            ].map(([k, v, ch], i) => (
              <div key={i} className="bg-panel p-4">
                <p className="text-xs text-dim">{k as string}</p>
                <p className="mt-1 font-mono text-2xl font-medium tabular-nums">{v as string}</p>
                {ch != null && <p className={cn("font-mono text-xs", (ch as number) >= 0 ? "text-up" : "text-down")}>{pc(ch as number, 2)} in 24h</p>}
              </div>
            ))}
          </section>

          <section className="grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
            {drivers.map((x) => <DriverCard key={x.id} d={x} />)}
            {!drivers.length && <div className="h-40 animate-pulse bg-panel sm:col-span-2 lg:col-span-3" />}
          </section>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <Box title="Bitcoin against the S&P 500" right={<span className="text-xs text-dim">90 days, both start at 100</span>} pad={false}>
              <div className="h-72 p-2"><Compare sp={drivers.find((x) => x.id === "SP500")} /></div>
            </Box>
            <Box title="Crowd mood" pad={false}><div className="h-72"><FearGreed series={m?.fear_greed ?? []} /></div></Box>
          </div>
        </div>

        <div className="space-y-4">
          <Box title="The desk" right={<Link to="/desk" className="flex items-center gap-1 text-xs text-dim hover:text-fg">Open <ArrowRight className="size-3" /></Link>}>
            <div className="flex items-center gap-3">
              <Avatar id="pm" size={52} mood={live ? "working" : pm ? "done" : "idle"} />
              <div className="min-w-0 flex-1">
                <p className="text-xs text-dim">{live ? "Working right now" : latest ? `Last run ${new Date(latest.started_at).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })}` : "No runs yet"}</p>
                <p className="line-clamp-2 text-[15px] leading-snug font-semibold">{live ? "Working on it" : latest?.summary ? latest.summary.split("\n")[0] : pm ? "Decision ready" : "No call yet"}</p>
              </div>
              <Button size="sm" onClick={d.runNow} disabled={live} className="gap-1.5"><Play className="size-3.5" />Run</Button>
            </div>
            {pm && <Prose html={pm.html} strip="h1" className="mt-3 max-h-56 overflow-y-auto text-[13px]" />}
            {waiting.length > 0 && (
              <Link to="/trades" className="mt-3 flex items-center justify-between rounded-md bg-brand-soft px-3 py-2 text-sm font-medium text-brand-strong">
                {waiting.length} plan{waiting.length > 1 ? "s" : ""} waiting for you <ArrowRight className="size-4" />
              </Link>
            )}
          </Box>

          <Box title="Tell the desk" right={<span className="text-xs text-dim">Read before every decision</span>}>
            <form onSubmit={(e) => { e.preventDefault(); if (note.trim()) { d.addNote({ kind: "note", text: note }); setNote(""); } }} className="space-y-2">
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="A view, a worry, an event to respect. E.g. 'CPI on the 10th, keep size small until then'" className="min-h-20 text-sm" />
              <Button size="sm" type="submit" disabled={!note.trim()}>Send to the desk</Button>
            </form>
            {d.notes.filter((n) => !n.asset).slice(0, 3).map((n) => (
              <p key={n.id} className="mt-2 rounded-md bg-sunk px-2.5 py-1.5 text-[13px]">{n.text}</p>
            ))}
          </Box>

          <Box title="Headlines" right={<Link to="/news" className="flex items-center gap-1 text-xs text-dim hover:text-fg">All news <ArrowRight className="size-3" /></Link>} pad={false}>
            <ul className="divide-y divide-line/60">
              {d.news.slice(0, 8).map((h) => (
                <li key={h.link}>
                  <a href={h.link} target="_blank" rel="noreferrer" className="flex gap-3 px-4 py-2.5 hover:bg-raised/50">
                    <span className="w-7 shrink-0 font-mono text-[11px] text-dim">{ago(h.ts)}</span>
                    <span className="min-w-0 text-[13px] leading-snug">{h.title}<span className="mt-0.5 block text-[11px] text-dim">{h.source}</span></span>
                  </a>
                </li>
              ))}
            </ul>
          </Box>
        </div>
      </div>
    </Page>
  );
}
