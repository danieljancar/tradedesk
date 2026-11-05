import { useMemo, useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router";
import { Crosshair, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Box, Page } from "@/components/shell";
import { MarketChart, cssColor, type LineSpec, type MarkerSpec, type Overlay } from "@/components/market-chart";
import { Positioning } from "@/components/positioning";
import { Prose } from "@/components/prose";
import { Term } from "@/components/term";
import { useTickers } from "@/components/terminal";
import { useDeskCtx } from "@/lib/desk-context";
import { pc, px, readAsset } from "@/lib/learn";
import type { Candle } from "@/lib/api";
import { cn } from "@/lib/utils";

const TFS = ["1h", "4h", "1d", "1w"] as const;
const SOURCE: Record<string, string> = { scan: "found by the scan", gold: "gold", always: "always watched", core: "core holding", watchlist: "watchlist" };
const ts = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);

function Toggle({ on, onClick, children, swatch }: { on: boolean; onClick: () => void; children: React.ReactNode; swatch?: string }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={cn("flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors",
        on ? "border-line bg-raised text-fg" : "border-transparent text-dim hover:text-fg")}>
      {swatch && <span className="h-0.5 w-3 rounded" style={{ background: swatch }} />}{children}
    </button>
  );
}

function technicalSection(body: string | null | undefined, asset: string) {
  if (!body) return null;
  const parts = body.split(/^## /m).slice(1);
  const hit = parts.find((p) => p.toUpperCase().startsWith(asset));
  return hit ? `## ${hit}` : null;
}

export default function Markets() {
  const d = useDeskCtx();
  const nav = useNavigate();
  const { asset: param } = useParams();
  const asset = (param ?? d.watch[0] ?? "BTC").toUpperCase();
  const ticks = useTickers(d.watch);
  const [tf, setTf] = useState<(typeof TFS)[number]>("4h");
  const [ov, setOv] = useState<Overlay>({ ema: true, volume: true, levels: true, plans: true, mine: true });
  const [drawing, setDrawing] = useState(false);
  const [pending, setPending] = useState<number | null>(null);
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [hover, setHover] = useState<Candle | null>(null);

  const byAsset = Object.fromEntries(d.universe.map((u) => [u.asset, u]));
  const found = d.universe.filter((u) => u.source === "scan").length;
  const pick = byAsset[asset];
  const f = d.facts?.[asset];
  const r = f?.frames ? readAsset(asset, f) : null;
  const t = ticks[asset];
  const plans = (d.state?.plans ?? []).filter((p) => p.asset === asset);
  const open = (d.state?.positions ?? []).filter((p) => p.asset === asset);
  const closed = (d.state?.closed ?? []).filter((p) => p.asset === asset);
  const mine = d.notes.filter((n) => n.asset === asset);
  const tech = [...d.events].reverse().find((e) => e.actor === "technical" && e.kind !== "start" && e.body);
  const techRead = technicalSection(tech?.body, asset);

  const lines = useMemo<LineSpec[]>(() => {
    const out: LineSpec[] = [];
    const up = cssColor("--up"), down = cssColor("--down"), brand = cssColor("--brand"), mineC = cssColor("--ema50"), fg = cssColor("--t-fg");
    const price = t?.price ?? f?.price;
    if (ov.levels && f?.levels && price) {
      const lv = f.levels[tf === "1h" || tf === "4h" ? "4h" : "1d"] ?? {};
      (lv.support ?? []).filter((x: number) => x < price).sort((a: number, b: number) => b - a).slice(0, 2).forEach((x: number) => out.push({ price: x, title: "support", color: up }));
      (lv.resistance ?? []).filter((x: number) => x > price).sort((a: number, b: number) => a - b).slice(0, 2).forEach((x: number) => out.push({ price: x, title: "resistance", color: down }));
    }
    if (ov.plans) {
      for (const p of plans.filter((p) => ["proposed", "approved", "placed"].includes(p.status))) {
        out.push({ price: p.entry, title: `plan ${p.side} entry`, color: brand, style: "solid", width: 2 });
        out.push({ price: p.stop, title: "plan stop", color: down, style: "solid" });
        out.push({ price: p.take_profit, title: "plan target", color: up, style: "solid" });
      }
      for (const p of open) {
        out.push({ price: p.entry_price, title: `${p.side} entry`, color: fg, style: "solid", width: 2 });
        out.push({ price: p.stop, title: "stop", color: down, style: "solid", width: 2 });
        out.push({ price: p.take_profit, title: "target", color: up, style: "solid", width: 2 });
      }
    }
    if (ov.mine) for (const n of mine.filter((n) => n.price != null)) out.push({ price: n.price!, title: n.text.slice(0, 18), color: mineC, style: "dotted", width: 2 });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ov, f, tf, JSON.stringify(plans), JSON.stringify(open), JSON.stringify(mine), Math.round((t?.price ?? 0) / 100)]);

  const markers = useMemo<MarkerSpec[]>(() => {
    if (!ov.plans) return [];
    const up = cssColor("--up"), down = cssColor("--down");
    const out: MarkerSpec[] = [];
    for (const p of [...open, ...closed]) {
      const long = p.side === "long";
      out.push({ time: ts(p.opened_at), text: `${p.side}`, color: long ? up : down, position: long ? "belowBar" : "aboveBar", shape: long ? "arrowUp" : "arrowDown" });
      if (p.closed_at) out.push({ time: ts(p.closed_at), text: `${p.pnl >= 0 ? "+" : ""}${Number(p.pnl).toFixed(2)}`, color: p.pnl >= 0 ? up : down, position: long ? "aboveBar" : "belowBar", shape: "circle" });
    }
    return out;
  }, [ov.plans, open, closed]);

  const saveLevel = async () => {
    if (pending == null) return;
    await d.addNote({ kind: "level", asset, price: Number(pending.toPrecision(6)), text: label.trim() || "my level" });
    setPending(null); setLabel(""); setDrawing(false);
  };

  return (
    <Page className="max-w-none">
      <div className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)_340px]">
        <Box title="Today's assets" right={found > 0 && <span className="text-xs text-dim">{found} from the scan</span>} pad={false} className="xl:self-start">
          <ul className="flex gap-1 overflow-x-auto p-1.5 xl:block xl:space-y-0.5">
            {d.watch.map((a) => {
              const k = ticks[a];
              const u = byAsset[a];
              return (
                <li key={a} className="shrink-0">
                  <NavLink to={`/markets/${a}`} title={u?.reason ?? undefined} className={({ isActive }) => cn("flex items-center justify-between gap-3 rounded-md px-2.5 py-2 hover:bg-raised", (isActive || (!param && a === asset)) && "bg-raised")}>
                    <span>
                      <span className="block font-semibold">{a}</span>
                      {u && u.source !== "watchlist" && <span className="block text-[10px] font-medium text-dim">{SOURCE[u.source]}</span>}
                    </span>
                    <span className="text-right">
                      <span className="block font-mono text-[13px] tabular-nums">{k ? px(k.price) : "–"}</span>
                      <span className={cn("block font-mono text-[11px] tabular-nums", k && (k.ch >= 0 ? "text-up" : "text-down"))}>{k ? pc(k.ch, 2) : ""}</span>
                    </span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </Box>

        <div className="min-w-0 space-y-4">
          <section className="overflow-hidden rounded-xl border border-line bg-panel">
            <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line px-4 py-3">
              <div>
                <p className="text-xs text-dim">{asset}/USDT{pick?.asset_class === "gold" ? ", one token is one troy ounce of gold" : ""}</p>
                <p className="font-mono text-2xl font-medium tabular-nums">{px(t?.price ?? f?.price)}
                  <span className={cn("ml-2 text-sm", t && (t.ch >= 0 ? "text-up" : "text-down"))}>{t ? pc(t.ch, 2) : ""}</span></p>
              </div>
              {f?.frames && (
                <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
                  <div><dt className="text-dim"><Term k="rsi">RSI 1d</Term></dt><dd className="font-mono">{f.frames["1d"]?.rsi?.toFixed(0)}</dd></div>
                  <div><dt className="text-dim"><Term k="atr">ATR 1d</Term></dt><dd className="font-mono">{f.frames["1d"]?.atr_pct?.toFixed(1)}%</dd></div>
                  <div><dt className="text-dim"><Term k="funding">Funding</Term></dt><dd className="font-mono">{f.derivatives ? `${f.derivatives.funding_pct.toFixed(4)}%` : "–"}</dd></div>
                  <div><dt className="text-dim"><Term k="longshort">Long/short</Term></dt><dd className="font-mono">{f.derivatives?.long_short_ratio?.toFixed(2) ?? "–"}</dd></div>
                  <div><dt className="text-dim">7 days, 30 days</dt><dd className="font-mono"><span className={f.change?.["7d"] >= 0 ? "text-up" : "text-down"}>{pc(f.change?.["7d"])}</span> <span className={f.change?.["30d"] >= 0 ? "text-up" : "text-down"}>{pc(f.change?.["30d"])}</span></dd></div>
                </dl>
              )}
              {pick?.reason && pick.source === "scan" && (
              <p className="w-full rounded-md bg-brand-soft px-3 py-1.5 text-[13px] text-brand-strong">Picked by the scan: {pick.reason}</p>
            )}
            {hover && (
                <p className="ml-auto font-mono text-[11px] text-dim">
                  O <span className="text-fg">{px(hover.open)}</span> H <span className="text-fg">{px(hover.high)}</span> L <span className="text-fg">{px(hover.low)}</span> C <span className="text-fg">{px(hover.close)}</span>
                </p>
              )}
            </header>
            <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-3 py-2">
              <div className="flex rounded-md bg-sunk p-0.5">
                {TFS.map((x) => (
                  <button key={x} type="button" onClick={() => setTf(x)} aria-pressed={tf === x}
                    className={cn("h-6 rounded-[5px] px-2.5 text-xs font-medium", tf === x ? "bg-raised text-fg shadow-sm" : "text-dim hover:text-fg")}>{x}</button>
                ))}
              </div>
              <span className="mx-1 h-5 w-px bg-line" />
              <Toggle on={ov.ema} onClick={() => setOv({ ...ov, ema: !ov.ema })} swatch="var(--ema20)">EMA 20/50/200</Toggle>
              <Toggle on={ov.volume} onClick={() => setOv({ ...ov, volume: !ov.volume })}>Volume</Toggle>
              <Toggle on={ov.levels} onClick={() => setOv({ ...ov, levels: !ov.levels })} swatch="var(--up)">Desk levels</Toggle>
              <Toggle on={ov.plans} onClick={() => setOv({ ...ov, plans: !ov.plans })} swatch="var(--brand)">Plans &amp; trades</Toggle>
              <Toggle on={ov.mine} onClick={() => setOv({ ...ov, mine: !ov.mine })} swatch="var(--ema50)">My levels</Toggle>
              <Button size="sm" variant={drawing ? "default" : "outline"} className="ml-auto h-7 gap-1.5 text-xs" onClick={() => { setDrawing(!drawing); setPending(null); }}>
                <Crosshair className="size-3.5" />{drawing ? "Click the chart to place it" : "Draw level"}
              </Button>
            </div>
            {pending != null && (
              <form className="flex flex-wrap items-center gap-2 border-b border-line bg-brand-soft px-3 py-2" onSubmit={(e) => { e.preventDefault(); saveLevel(); }}>
                <span className="text-xs">Level at <b className="font-mono">{px(pending)}</b></span>
                <Input autoFocus value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label, e.g. weekly support" className="h-8 max-w-sm flex-1 text-sm" />
                <Button size="sm" type="submit" className="h-8">Save for the desk</Button>
                <Button size="sm" type="button" variant="ghost" className="h-8" onClick={() => setPending(null)}>Cancel</Button>
              </form>
            )}
            <div className="h-[56vh] min-h-[360px]">
              <MarketChart asset={asset} tf={tf} overlay={ov} lines={lines} markers={markers} drawing={drawing} onPick={setPending} onHover={setHover} />
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Box title="The desk's chart read" right={tech && <span className="text-xs text-dim">Tech analyst, {new Date(tech.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}>
              {techRead ? <Prose html={techRead.replace(/^## (.*)$/m, "").trim().split("\n").map((l) => `<p>${l.replace(/</g, "&lt;")}</p>`).join("")} className="text-[13px]" />
                : <p className="text-sm text-dim">No chart read for {asset} in the latest run. Run the desk to get one.</p>}
              {r && <p className="mt-3 rounded-md bg-sunk px-3 py-2 text-[13px]">{r.headline}</p>}
            </Box>
            <Box title={`Plans and trades on ${asset}`}>
              {!plans.length && !open.length && !closed.length && <p className="text-sm text-dim">Nothing yet on {asset}.</p>}
              <ul className="space-y-2 text-[13px]">
                {open.map((p) => <li key={`o${p.id}`} className="flex justify-between gap-2"><span><b className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</b> open at {px(p.entry_price)}</span><span className="font-mono text-dim">stop {px(p.stop)}, target {px(p.take_profit)}</span></li>)}
                {plans.slice(0, 6).map((p) => <li key={`p${p.id}`} className="flex justify-between gap-2"><span><b className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</b> plan, {p.status}</span><span className="font-mono text-dim">{px(p.entry)} / {px(p.stop)} / {px(p.take_profit)}</span></li>)}
                {closed.slice(0, 5).map((p) => <li key={`c${p.id}`} className="flex justify-between gap-2"><span>{p.side} closed, {p.exit_reason}</span><span className={cn("font-mono", p.pnl >= 0 ? "text-up" : "text-down")}>{p.pnl >= 0 ? "+" : ""}{Number(p.pnl).toFixed(2)}</span></li>)}
              </ul>
            </Box>
          </div>
          <Positioning asset={asset} />
        </div>

        <div className="space-y-4">
          <Box title={`Signals, ${asset}`} pad={false}>
            {r ? (
              <dl className="divide-y divide-line/60">
                {r.lines.map((l) => (
                  <div key={l.key} className="px-4 py-2.5">
                    <div className="flex items-center justify-between gap-3 text-[13px]">
                      <dt><Term k={l.term}>{l.label}</Term></dt>
                      <dd className={cn("font-mono tabular-nums", l.tone === "up" && "text-up", l.tone === "down" && "text-down", l.tone === "warn" && "text-warn")}>{l.value}</dd>
                    </div>
                    <p className="mt-0.5 text-xs leading-snug text-dim">{l.text}</p>
                  </div>
                ))}
              </dl>
            ) : <p className="p-4 text-sm text-dim">No snapshot for {asset} yet. It appears after the next desk run.</p>}
          </Box>
          <Box title="My levels and notes" right={<span className="text-xs text-dim">The desk reads these</span>}>
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (note.trim()) { d.addNote({ kind: "idea", asset, text: note }); setNote(""); } }}>
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder={`Note on ${asset}`} className="min-h-16 text-sm" />
              <Button size="sm" type="submit" disabled={!note.trim()}>Add note</Button>
            </form>
            <ul className="mt-3 space-y-1.5">
              {mine.map((n) => (
                <li key={n.id} className="group flex items-start gap-2 rounded-md bg-sunk px-2.5 py-1.5 text-[13px]">
                  <span className="flex-1">{n.price != null && <b className="mr-1.5 font-mono">{px(n.price)}</b>}{n.text}</span>
                  <button type="button" onClick={() => d.dropNote(n.id)} aria-label="Remove" className="text-dim opacity-60 hover:text-down hover:opacity-100"><Trash2 className="size-3.5" /></button>
                </li>
              ))}
              {!mine.length && <li className="text-xs text-dim">Use "Draw level" or add a note.</li>}
            </ul>
          </Box>
          <p className="px-1 text-[11px] text-dim">Switch coin: {d.watch.filter((a) => a !== asset).map((a) => <button key={a} className="mr-2 underline-offset-2 hover:underline" onClick={() => nav(`/markets/${a}`)}>{a}</button>)}</p>
        </div>
      </div>
    </Page>
  );
}
