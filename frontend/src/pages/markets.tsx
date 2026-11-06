import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router";
import { ChevronLeft, ChevronRight, Crosshair, Layers, Maximize2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { usePref } from "@/lib/prefs";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Box, Page } from "@/components/shell";
import { AssetGroup } from "@/components/asset-list";
import { MarketChart, cssColor, type RangeSpec, type BoxSpec, type LineSpec, type MarkerSpec, type Overlay, type SegmentSpec } from "@/components/market-chart";
import { Positioning } from "@/components/positioning";
import { Prose } from "@/components/prose";
import { Term } from "@/components/term";
import { useTickers } from "@/components/terminal";
import { useDeskCtx } from "@/lib/desk-context";
import { pc, planSize, px, readAsset } from "@/lib/learn";
import type { Candle } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useApi } from "@/lib/query";

const TFS = ["1h", "4h", "1d", "1w", "1M"] as const;
const TF_LABEL: Record<string, string> = { "1M": "1mo" };
const DAY = 86_400;
// each window picks a bar size that fits it, like TradingView's range buttons
const RANGES: { label: string; days: number | null; tf: (typeof TFS)[number] }[] = [
  { label: "1W", days: 7, tf: "1h" },
  { label: "1M", days: 30, tf: "4h" },
  { label: "3M", days: 91, tf: "4h" },
  { label: "1Y", days: 365, tf: "1d" },
  { label: "5Y", days: 5 * 365, tf: "1w" },
  { label: "All", days: null, tf: "1M" },
];
// charted from FRED daily closes, so only daily and weekly bars
const INDEXES: Record<string, { name: string; driver: string }> = {
  SPX: { name: "S&P 500", driver: "SP500" },
  NDX: { name: "Nasdaq Composite", driver: "NASDAQCOM" },
};
type Scale = "short" | "mid" | "long";
const SCALES: { key: Scale; label: string; tf: string; width: 1 | 2 | 3; style: "solid" | "dashed" | "dotted" }[] = [
  { key: "long", label: "Long term", tf: "1w", width: 3, style: "solid" },
  { key: "mid", label: "Mid term", tf: "1d", width: 2, style: "dashed" },
  { key: "short", label: "Short term", tf: "4h", width: 1, style: "dotted" },
];
type Shape = { pattern: string; position: string; tf: string; upper: { t1: number; p1: number; t_end: number; p_end: number }; lower: { t1: number; p1: number; t_end: number; p_end: number } };
type Patterns = Record<Scale, Shape | null> & { levels: { price: number; touches: number; since: number; kind: "support" | "resistance" }[] };
const SOURCE: Record<string, string> = { scan: "scan pick", gold: "gold", always: "always on", core: "core holding", watchlist: "watchlist" };
const ts = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);

/** Half-round handle on the panel it hides. With the panel gone it waits on the page edge. */
function Edge({ side, open, onClick }: { side: "left" | "right"; open: boolean; onClick: () => void }) {
  const Icon = (side === "left") === open ? ChevronLeft : ChevronRight;
  const at = side === "left" ? (open ? "left-[219px]" : "-left-[19px]") : (open ? "right-[339px]" : "-right-[19px]");
  return (
    <button type="button" onClick={onClick} aria-label={`${open ? "Hide" : "Show"} the ${side === "left" ? "asset list" : "side panel"}`}
      className={cn("absolute top-40 z-20 hidden h-12 w-4 place-items-center border border-line bg-raised text-dim hover:text-fg xl:grid", at,
        side === "left" ? "rounded-r-full border-l-0" : "rounded-l-full border-r-0")}>
      <Icon className="size-3.5" />
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
  const { asset: param } = useParams();
  const asset = (param ?? d.watch[0] ?? "BTC").toUpperCase();
  const ticks = useTickers(d.watch);
  // layout and layers are remembered in this browser
  const [prefs, setPrefs] = usePref("markets.prefs", {
    tf: "4h" as (typeof TFS)[number], window: "" as string, left: true, right: true,
    ov: { ema: true, volume: true, levels: true, plans: true, mine: true } as Overlay,
    scales: { long: true, mid: true, short: true } as Record<Scale, boolean>,
  });
  const { tf, ov, scales } = prefs;
  const setTf = (x: (typeof TFS)[number]) => setPrefs({ ...prefs, tf: x, window: "" });
  const setOv = (x: Overlay) => setPrefs({ ...prefs, ov: x });
  const setScales = (x: Record<Scale, boolean>) => setPrefs({ ...prefs, scales: x });
  const [fit, setFit] = useState(0);
  const index = INDEXES[asset];
  useEffect(() => { if (index && tf.endsWith("h")) setTf("1d"); }, [index, tf]);
  const pat = useApi<Patterns>(`/api/patterns/${asset}`, { stale: 900_000, every: 900_000 }).data;
  const driver = index ? d.macro?.drivers?.find((x: any) => x.id === index.driver) : null;
  const [drawing, setDrawing] = useState(false);
  const [pending, setPending] = useState<number | null>(null);
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [hover, setHover] = useState<Candle | null>(null);
  const [range, setRange] = useState<RangeSpec | undefined>();
  const pickRange = (r: (typeof RANGES)[number]) => {
    const daily = index && (r.tf === "1h" || r.tf === "4h");
    setPrefs({ ...prefs, tf: daily ? "1d" : r.tf, window: r.label });
    setRange({ from: r.days == null ? null : Math.floor(Date.now() / 1000) - r.days * DAY, n: (range?.n ?? 0) + 1 });
  };
  // the saved window comes back with the page
  useEffect(() => {
    const r = RANGES.find((x) => x.label === prefs.window);
    if (r) setRange({ from: r.days == null ? null : Math.floor(Date.now() / 1000) - r.days * DAY, n: 1 });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const byAsset = Object.fromEntries(d.universe.map((u) => [u.asset, u]));
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
    if (scales.long) {
      for (const l of pat?.levels ?? []) {
        out.push({ price: l.price, title: `${l.touches}× weekly ${l.kind}`, color: cssColor(l.kind === "support" ? "--up" : "--down", 0.55), style: "solid", width: 1 });
      }
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ov, f, tf, scales.long, JSON.stringify(pat?.levels), JSON.stringify(plans), JSON.stringify(open), JSON.stringify(mine), Math.round((t?.price ?? 0) / 100)]);

  const shapes = SCALES.map((s) => ({ ...s, shape: pat?.[s.key] ?? null })).filter((s) => s.shape);
  const segments = useMemo<SegmentSpec[]>(() => {
    const c = cssColor("--ema200");
    // short-term lines only make sense on the short charts
    return shapes
      .filter((s) => scales[s.key] && !(s.key === "short" && !tf.endsWith("h")))
      .flatMap((s) => (["upper", "lower"] as const).map((k) => ({
        t1: s.shape![k].t1, p1: s.shape![k].p1, t2: s.shape![k].t_end, p2: s.shape![k].p_end,
        color: c, width: s.width, style: s.style, extend: true,
      })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tf, JSON.stringify(scales), JSON.stringify(shapes)]);

  const boxes = useMemo<BoxSpec[]>(() => {
    if (!ov.plans) return [];
    const up = cssColor("--up", 0.12), down = cssColor("--down", 0.12);
    return [
      ...plans.filter((p) => ["proposed", "approved", "placed"].includes(p.status)).map((p) => ({ from: ts(p.created_at), entry: p.entry, stop: p.stop, target: p.take_profit, up, down })),
      ...open.map((p) => ({ from: ts(p.opened_at), entry: p.entry_price, stop: p.stop, target: p.take_profit, up, down })),
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ov.plans, JSON.stringify(plans), JSON.stringify(open)]);

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
      <div className={cn("relative grid gap-4",
        prefs.left && prefs.right && "xl:grid-cols-[220px_minmax(0,1fr)_340px]",
        prefs.left && !prefs.right && "xl:grid-cols-[220px_minmax(0,1fr)]",
        !prefs.left && prefs.right && "xl:grid-cols-[minmax(0,1fr)_340px]")}>
        <Edge side="left" open={prefs.left} onClick={() => setPrefs({ ...prefs, left: !prefs.left })} />
        <Edge side="right" open={prefs.right} onClick={() => setPrefs({ ...prefs, right: !prefs.right })} />
        {prefs.left && <Box pad={false} className="xl:self-start">
          <div className="flex gap-2 overflow-x-auto p-1.5 xl:block xl:space-y-2">
            <AssetGroup id="coins" title="Coins" active={asset} rows={d.watch.map((a) => {
              const k = ticks[a], u = byAsset[a];
              return {
                id: a, label: a, title: u?.reason ?? undefined,
                sub: u && u.source !== "watchlist" ? SOURCE[u.source] : undefined,
                value: k ? px(k.price) : undefined,
                change: k && <span className={cn("block font-mono text-[11px] tabular-nums", k.ch >= 0 ? "text-up" : "text-down")}>{pc(k.ch, 2)}</span>,
              };
            })} />
            <AssetGroup id="indexes" title="Indexes" active={asset} rows={Object.entries(INDEXES).map(([k, ix]) => {
              const dr = d.macro?.drivers?.find((x: any) => x.id === ix.driver);
              return {
                id: k, label: ix.name,
                value: dr?.value != null ? px(dr.value) : undefined,
                change: dr?.change_1w != null && <span className={cn("block font-mono text-[11px] tabular-nums", dr.change_1w >= 0 ? "text-up" : "text-down")}>{pc(dr.change_1w, 2)} 1w</span>,
              };
            })} />
          </div>
        </Box>}

        <div className="min-w-0 space-y-4">
          <section className="overflow-hidden rounded-xl border border-line bg-panel">
            <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line px-4 py-3">
              <div>
                {index ? (
                  <>
                    <p className="text-xs text-dim">{index.name}, daily closes from FRED{driver?.as_of ? `, last ${driver.as_of}` : ""}</p>
                    <p className="font-mono text-2xl font-medium tabular-nums">{driver?.value != null ? px(driver.value) : "–"}
                      <span className={cn("ml-2 text-sm", driver?.change_1w != null && (driver.change_1w >= 0 ? "text-up" : "text-down"))}>{driver?.change_1w != null ? `${pc(driver.change_1w, 2)} 1w` : ""}</span></p>
                  </>
                ) : (
                  <>
                    <p className="text-xs text-dim">{asset}/USDT{pick?.asset_class === "gold" ? ", one token is one troy ounce of gold" : ""}</p>
                    <p className="font-mono text-2xl font-medium tabular-nums">{px(t?.price ?? f?.price)}
                      <span className={cn("ml-2 text-sm", t && (t.ch >= 0 ? "text-up" : "text-down"))}>{t ? pc(t.ch, 2) : ""}</span></p>
                  </>
                )}
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
            </header>
            <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-3 py-2">
              <div className="flex rounded-md bg-sunk p-0.5">
                {TFS.filter((x) => !index || !x.endsWith("h")).map((x) => (
                  <button key={x} type="button" onClick={() => setTf(x)} aria-pressed={tf === x}
                    className={cn("h-6 rounded-[5px] px-2.5 text-xs font-medium", tf === x ? "bg-raised text-fg shadow-sm" : "text-dim hover:text-fg")}>{TF_LABEL[x] ?? x}</button>
                ))}
              </div>
              <div className="flex rounded-md bg-sunk p-0.5" aria-label="Time window">
                {RANGES.filter((r) => !index || r.label !== "1W").map((r) => (
                  <button key={r.label} type="button" onClick={() => pickRange(r)} aria-pressed={prefs.window === r.label}
                    className={cn("h-6 rounded-[5px] px-2 text-xs font-medium", prefs.window === r.label ? "bg-raised text-fg shadow-sm" : "text-dim hover:text-fg")}>{r.label}</button>
                ))}
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs"><Layers className="size-3.5" />Layers</Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-52">
                  <DropdownMenuLabel>Indicators</DropdownMenuLabel>
                  <DropdownMenuCheckboxItem checked={ov.ema} onCheckedChange={(v) => setOv({ ...ov, ema: !!v })} onSelect={(e) => e.preventDefault()}>EMA 20, 50, 200</DropdownMenuCheckboxItem>
                  {!index && <DropdownMenuCheckboxItem checked={ov.volume} onCheckedChange={(v) => setOv({ ...ov, volume: !!v })} onSelect={(e) => e.preventDefault()}>Volume</DropdownMenuCheckboxItem>}
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel>Patterns</DropdownMenuLabel>
                  {SCALES.filter((x) => !index || x.key !== "short").map((x) => (
                    <DropdownMenuCheckboxItem key={x.key} checked={scales[x.key]} onCheckedChange={(v) => setScales({ ...scales, [x.key]: !!v })} onSelect={(e) => e.preventDefault()}>{x.label} ({x.tf})</DropdownMenuCheckboxItem>
                  ))}
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel>Levels</DropdownMenuLabel>
                  {!index && <DropdownMenuCheckboxItem checked={ov.levels} onCheckedChange={(v) => setOv({ ...ov, levels: !!v })} onSelect={(e) => e.preventDefault()}>Desk levels</DropdownMenuCheckboxItem>}
                  {!index && <DropdownMenuCheckboxItem checked={ov.plans} onCheckedChange={(v) => setOv({ ...ov, plans: !!v })} onSelect={(e) => e.preventDefault()}>Plans and trades</DropdownMenuCheckboxItem>}
                  <DropdownMenuCheckboxItem checked={ov.mine} onCheckedChange={(v) => setOv({ ...ov, mine: !!v })} onSelect={(e) => e.preventDefault()}>My levels</DropdownMenuCheckboxItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs" onClick={() => { setFit((x) => x + 1); setPrefs({ ...prefs, window: "" }); }} title="Back to the latest bars, fitted to the chart">
                <Maximize2 className="size-3.5" />Fit
              </Button>
              <Button size="sm" variant={drawing ? "default" : "outline"} className="h-7 gap-1.5 text-xs" onClick={() => { setDrawing(!drawing); setPending(null); }}>
                <Crosshair className="size-3.5" />{drawing ? "Click the chart" : "Draw level"}
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
            <div className={cn("relative min-h-[360px]", prefs.left || prefs.right ? "h-[56vh]" : "h-[72vh]")}>
              {hover && (
                <p className="pointer-events-none absolute top-2 left-3 z-10 font-mono text-[11px] text-dim">
                  O <span className="text-fg">{px(hover.open)}</span> H <span className="text-fg">{px(hover.high)}</span> L <span className="text-fg">{px(hover.low)}</span> C <span className="text-fg">{px(hover.close)}</span>
                </p>
              )}
              <MarketChart asset={asset} tf={tf} range={range} fit={fit} live={!index} overlay={index ? { ...ov, volume: false } : ov} lines={lines} markers={markers} segments={segments} boxes={boxes} drawing={drawing} onPick={setPending} onHover={setHover} />
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Box title="The desk's chart read" right={tech && <span className="text-xs text-dim">Tech analyst, {new Date(tech.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}>
              {techRead ? <Prose html={techRead.replace(/^## (.*)$/m, "").trim().split("\n").map((l) => `<p>${l.replace(/</g, "&lt;")}</p>`).join("")} className="text-[13px]" />
                : !index && <p className="text-sm text-dim">No chart read for {asset} in the latest run. Run the desk to get one.</p>}
              {r && <p className="mt-3 rounded-md bg-sunk px-3 py-2 text-[13px]">{r.headline}</p>}
              {shapes.length > 0 && (
                <ul className="mt-2 space-y-1 text-[13px]">
                  {shapes.map((s) => <li key={s.key}><span className="text-dim">{s.label} ({s.tf}):</span> {s.shape!.pattern}, price {s.shape!.position}</li>)}
                  {!!pat?.levels.length && <li><span className="text-dim">Weekly levels:</span> {pat.levels.map((l) => `${px(l.price)} (${l.touches}×)`).join(", ")}</li>}
                </ul>
              )}
            </Box>
            {!index && <Box title={`Plans and trades on ${asset}`}>
              {!plans.length && !open.length && !closed.length && <p className="text-sm text-dim">Nothing yet on {asset}.</p>}
              <ul className="space-y-2 text-[13px]">
                {open.map((p) => <li key={`o${p.id}`} className="flex justify-between gap-2"><span><b className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</b> open at {px(p.entry_price)}</span><span className="font-mono text-dim">stop {px(p.stop)}, target {px(p.take_profit)}</span></li>)}
                {plans.slice(0, 6).map((p) => <li key={`p${p.id}`} className="flex justify-between gap-2"><span><b className={p.side === "long" ? "text-up" : "text-down"}>{p.side}</b> plan, {p.status}</span><span className="font-mono text-dim">{px(p.entry)} / {px(p.stop)} / {px(p.take_profit)}{planSize(p).value ? `, ${planSize(p).value.toFixed(2)} USDT` : ""}</span></li>)}
                {closed.slice(0, 5).map((p) => <li key={`c${p.id}`} className="flex justify-between gap-2"><span>{p.side} closed, {p.exit_reason}</span><span className={cn("font-mono", p.pnl >= 0 ? "text-up" : "text-down")}>{p.pnl >= 0 ? "+" : ""}{Number(p.pnl).toFixed(2)}</span></li>)}
              </ul>
            </Box>}
          </div>
          {!index && <Positioning asset={asset} />}
        </div>

        {prefs.right && <div className="space-y-4">
          {!index && <Box title={`Signals, ${asset}`} pad={false}>
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
          </Box>}
          <Box title="My levels and notes" right={<span className="text-xs text-dim">The desk reads these</span>}>
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (note.trim()) { d.addNote({ kind: "idea", asset, text: note }); setNote(""); } }}>
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder={`Note on ${asset}`} className="min-h-16 text-sm" />
              <Button size="sm" type="submit" disabled={!note.trim()}>Add note</Button>
            </form>
            <ul className="mt-3 space-y-1.5">
              {mine.map((n) => (
                <li key={n.id} className="group flex items-start gap-2 rounded-md bg-sunk px-2.5 py-1.5 text-[13px]">
                  <span className="flex-1">{n.price != null && <b className="mr-1.5 font-mono">{px(n.price)}</b>}{n.text}</span>
                  <button type="button" onClick={() => d.dropNote(n.id)} aria-label={`Delete ${n.text}`} className="-my-1 -mr-1.5 grid size-7 shrink-0 place-items-center rounded-md text-dim hover:bg-down/10 hover:text-down"><Trash2 className="size-4" /></button>
                </li>
              ))}
              {!mine.length && <li className="text-xs text-dim">Use "Draw level" or add a note.</li>}
            </ul>
          </Box>
        </div>}
      </div>
    </Page>
  );
}
