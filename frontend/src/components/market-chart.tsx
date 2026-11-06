import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, LineStyle, createChart, createSeriesMarkers,
  type IChartApi, type IPriceLine, type ISeriesApi, type ISeriesMarkersPluginApi, type SeriesMarker, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { api, type Candle } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { useApi } from "@/lib/query";

const ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true })!;
export function cssColor(name: string, alpha = 1) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillStyle = "#000";
  ctx.fillStyle = raw;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
  return `rgba(${r}, ${g}, ${b}, ${((a / 255) * alpha).toFixed(3)})`;
}

function ema(values: number[], period: number) {
  const k = 2 / (period + 1);
  let prev: number | null = null;
  return values.map((v, i) => {
    if (i < period - 1) return null;
    prev = prev == null ? values.slice(0, period).reduce((a, b) => a + b, 0) / period : v * k + prev * (1 - k);
    return prev;
  });
}

export type Overlay = { ema: boolean; volume: boolean; levels: boolean; plans: boolean; mine: boolean };
export type SegmentSpec = { t1: number; p1: number; t2: number; p2: number; color: string; width?: 1 | 2 | 3; style?: "solid" | "dashed" | "dotted"; extend?: boolean };
export type BoxSpec = { from: number; entry: number; stop: number; target: number; up: string; down: string };
export type LineSpec = { price: number; title: string; color: string; style?: "solid" | "dashed" | "dotted"; width?: 1 | 2 | 3 };
/** A time window to show, `from` in seconds, null for all history. `n` changes on every click. */
export type RangeSpec = { from: number | null; n: number };
export type MarkerSpec = { time: number; text: string; color: string; position: "aboveBar" | "belowBar"; shape: "arrowUp" | "arrowDown" | "circle" };

const STYLES = { solid: LineStyle.Solid, dashed: LineStyle.Dashed, dotted: LineStyle.Dotted };
const SPAN: Record<string, number> = { "1h": 180, "4h": 180, "1d": 150, "1w": 120, "1M": 80 };
const t = (c: Candle) => c.time as UTCTimestamp;

type Handles = {
  chart: IChartApi;
  candles: ISeriesApi<"Candlestick">;
  vol: ISeriesApi<"Histogram"> | null;
  emas: [number, string, ISeriesApi<"Line">][];
  marks: ISeriesMarkersPluginApi<Time>;
  prices: IPriceLine[];
  segs: ISeriesApi<"Line">[];
};

// averages never stretch the price scale, the candles decide its height
const avgLine = (chart: IChartApi, color: string) =>
  chart.addSeries(LineSeries, { color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, autoscaleInfoProvider: () => null });

// the candle an event happened in
function barOf(data: Candle[], ts: number) {
  if (!data.length || ts < data[0].time) return null;
  let lo = 0, hi = data.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (data[mid].time <= ts) lo = mid; else hi = mid - 1; }
  return data[lo].time;
}

/** Candle chart. The chart is built once per coin and bar size; data, lines and zones update
 * in place, so refreshes never move what you're looking at. */
export function MarketChart({ asset, tf, overlay, lines, markers, segments = [], boxes = [], drawing, onPick, onHover, range, fit = 0, live = true }: {
  asset: string; tf: string; overlay: Overlay; lines: LineSpec[]; markers: MarkerSpec[]; segments?: SegmentSpec[]; boxes?: BoxSpec[];
  drawing: boolean; onPick: (price: number) => void; onHover?: (c: Candle | null) => void; range?: RangeSpec; fit?: number; live?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const paint = useRef<HTMLCanvasElement>(null);
  const h = useRef<Handles | null>(null);
  const [built, setBuilt] = useState(0);
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const hoverRef = useRef(onHover);
  hoverRef.current = onHover;
  const drawRef = useRef(drawing);
  drawRef.current = drawing;
  const boxesRef = useRef(boxes);
  boxesRef.current = boxes;

  const key = `${asset}:${tf}`;
  const limit = tf.endsWith("h") ? 500 : 1000;
  const q = useApi<Candle[]>(`/api/candles/${asset}?tf=${tf}&limit=${limit}`, { every: 60_000 });
  const err = q.data ? null : (q.error?.message ?? null);

  // older bars load in pages when you scroll to the left edge
  const [older, setOlder] = useState<{ key: string; bars: Candle[] }>({ key, bars: [] });
  const done = useRef(new Set<string>());
  const loading = useRef(false);
  const data = useMemo(() => {
    const fresh = q.data;
    if (!fresh?.length) return fresh ?? null;
    if (older.key !== key || !older.bars.length) return fresh;
    return [...older.bars.filter((c) => c.time < fresh[0].time), ...fresh];
  }, [q.data, older, key]);
  const dataRef = useRef<Candle[] | null>(null);
  const loadOlder = useRef(async () => {});
  loadOlder.current = async () => {
    const d = dataRef.current;
    if (!d?.length || loading.current || done.current.has(key)) return;
    loading.current = true;
    try {
      const got = await api<Candle[]>(`/api/candles/${asset}?tf=${tf}&limit=1000&end=${d[0].time * 1000 - 1}`);
      const fresh = got.filter((c) => c.time < d[0].time);
      if (fresh.length < 2) done.current.add(key);
      // a second page can come back before the chart saw the first one; only bars older than
      // what's already held go in front, or the time line gets duplicates and the chart crashes
      else setOlder((o) => {
        const held = o.key === key ? o.bars : [];
        const head = held[0]?.time ?? Infinity;
        return { key, bars: [...fresh.filter((c) => c.time < head), ...held] };
      });
    } catch {
      done.current.add(key);
    } finally {
      loading.current = false;
    }
  };

  const shown = useRef(false);
  const want = useRef<RangeSpec | null>(null);
  const fitAll = () => {
    const c = h.current, d = dataRef.current;
    if (!c || !d?.length) return;
    c.chart.priceScale("right").applyOptions({ autoScale: true });
    c.chart.timeScale().setVisibleLogicalRange({ from: d.length - (SPAN[tf] ?? 150), to: d.length + 5 });
  };
  const applyWant = () => {
    const c = h.current, d = dataRef.current, goal = want.current;
    if (!c || !d?.length || !goal) return;
    c.chart.priceScale("right").applyOptions({ autoScale: true });
    const from = goal.from ?? 0;
    if (d[0].time > from && !done.current.has(key)) loadOlder.current();
    else want.current = null;
    c.chart.timeScale().setVisibleRange({ from: Math.max(from, d[0].time) as UTCTimestamp, to: d[d.length - 1].time as UTCTimestamp });
  };

  const [scheme, setScheme] = useState(0);
  useEffect(() => {
    const mo = new MutationObserver(() => setScheme((x) => x + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => mo.disconnect();
  }, []);

  // build
  useEffect(() => {
    if (!box.current) return;
    const up = cssColor("--up"), down = cssColor("--down"), fg = cssColor("--t-dim"), grid = cssColor("--t-line");
    const chart = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: fg, fontFamily: "Geist Variable, sans-serif", fontSize: 11, attributionLogo: false },
      grid: { vertLines: { color: cssColor("--t-line", 0.5) }, horzLines: { color: cssColor("--t-line", 0.5) } },
      rightPriceScale: { borderColor: grid, scaleMargins: { top: 0.06, bottom: overlay.volume ? 0.2 : 0.06 } },
      timeScale: { borderColor: grid, timeVisible: tf.endsWith("h"), rightOffset: 6 },
      crosshair: { mode: CrosshairMode.Normal },
    });
    const candles = chart.addSeries(CandlestickSeries, { upColor: up, downColor: down, borderVisible: false, wickUpColor: up, wickDownColor: down });
    let vol: ISeriesApi<"Histogram"> | null = null;
    if (overlay.volume) {
      vol = chart.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    }
    // averages and pattern lines never stretch the price scale, the candles decide its height
    const emas: [number, string, ISeriesApi<"Line">][] = overlay.ema
      ? ([[20, "--ema20"], [50, "--ema50"], [200, "--ema200"]] as const).map(([n, c]) => [n, cssColor(c), avgLine(chart, cssColor(c))])
      : [];
    const marks = createSeriesMarkers(candles, [] as SeriesMarker<UTCTimestamp>[]);
    h.current = { chart, candles, vol, emas, marks, prices: [], segs: [] };
    shown.current = false;

    chart.subscribeClick((param) => {
      if (!drawRef.current || !param.point) return;
      const price = candles.coordinateToPrice(param.point.y);
      if (price != null) pickRef.current(Number(price));
    });
    chart.subscribeCrosshairMove((param) => {
      const d = dataRef.current;
      if (!d?.length) return;
      const c = param.time ? d.find((x) => x.time === param.time) : null;
      hoverRef.current?.(c ?? d[d.length - 1]);
    });
    chart.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (r && r.from < 30 && shown.current) loadOlder.current(); });

    // plan and position zones on a canvas over the chart: green to the target, red to the stop
    let frame = 0;
    const draw = () => {
      const cv = paint.current, el = box.current, d = dataRef.current;
      if (cv && el && d?.length) {
        const w = el.clientWidth, hh = el.clientHeight, dpr = devicePixelRatio || 1;
        if (cv.width !== w * dpr || cv.height !== hh * dpr) { cv.width = w * dpr; cv.height = hh * dpr; }
        const g = cv.getContext("2d")!;
        g.setTransform(dpr, 0, 0, dpr, 0, 0);
        g.clearRect(0, 0, w, hh);
        const right = w - (chart.priceScale("right").width() || 0);
        for (const bx of boxesRef.current) {
          const at = barOf(d, bx.from) ?? d[0].time;
          const x = chart.timeScale().timeToCoordinate(at as UTCTimestamp) ?? 0;
          const ye = candles.priceToCoordinate(bx.entry), ys = candles.priceToCoordinate(bx.stop), yt = candles.priceToCoordinate(bx.target);
          if (ye == null || ys == null || yt == null || x >= right) continue;
          g.fillStyle = bx.up; g.fillRect(x, Math.min(ye, yt), right - x, Math.abs(yt - ye));
          g.fillStyle = bx.down; g.fillRect(x, Math.min(ye, ys), right - x, Math.abs(ys - ye));
        }
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    // the forming candle ticks live from Binance's public stream; the 60s refetch fills gaps
    const us = cssColor("--up", 0.35), ds = cssColor("--down", 0.35);
    const ws = live ? new WebSocket(`wss://stream.binance.com:9443/ws/${asset.toLowerCase()}usdt@kline_${tf}`) : null;
    if (ws) ws.onmessage = (ev) => {
      const k = JSON.parse(ev.data)?.k;
      const d = dataRef.current;
      if (!k || !d?.length) return;
      const time = Math.floor(k.t / 1000) as UTCTimestamp;
      if (time < d[d.length - 1].time) return;
      const bar = { time, open: +k.o, high: +k.h, low: +k.l, close: +k.c };
      candles.update(bar);
      vol?.update({ time, value: +k.v, color: bar.close >= bar.open ? us : ds });
    };
    setBuilt((x) => x + 1);
    return () => {
      cancelAnimationFrame(frame);
      paint.current?.getContext("2d")?.clearRect(0, 0, 1e5, 1e5);
      ws?.close();
      chart.remove();
      h.current = null;
      dataRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, scheme, overlay.ema, overlay.volume, live]);

  // data
  useEffect(() => {
    const c = h.current;
    if (!c || !data?.length) return;
    const prev = dataRef.current;
    const ts = c.chart.timeScale();
    const before = ts.getVisibleLogicalRange();
    const grew = !!prev?.length && data[0].time < prev[0].time;
    c.candles.setData(data.map((x) => ({ time: t(x), open: x.open, high: x.high, low: x.low, close: x.close })));
    if (c.vol) {
      const us = cssColor("--up", 0.35), ds = cssColor("--down", 0.35);
      c.vol.setData(data.map((x) => ({ time: t(x), value: x.volume, color: x.close >= x.open ? us : ds })));
    }
    const closes = data.map((x) => x.close);
    for (const [n, , series] of c.emas) {
      const e = ema(closes, n);
      series.setData(data.flatMap((x, i) => (e[i] == null ? [] : [{ time: t(x), value: e[i]! }])));
    }
    dataRef.current = data;
    if (want.current) applyWant();
    else if (!shown.current) fitAll();
    else if (grew && before) {
      // older bars came in at the front: keep the same candles on screen
      const added = data.findIndex((x) => x.time === prev[0].time);
      if (added > 0) ts.setVisibleLogicalRange({ from: before.from + added, to: before.to + added });
    }
    shown.current = true;
    hoverRef.current?.(data[data.length - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, built]);

  // levels and trade lines
  useEffect(() => {
    const c = h.current;
    if (!c) return;
    for (const p of c.prices) c.candles.removePriceLine(p);
    c.prices = lines.map((l) => c.candles.createPriceLine({ price: l.price, color: l.color, lineWidth: l.width ?? 1, lineStyle: STYLES[l.style ?? "dashed"], axisLabelVisible: true, title: l.title }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(lines), built]);

  // pattern lines, cut to the bars loaded and run on to the last bar when asked
  const first = data?.[0]?.time, last = data?.[data.length - 1]?.time;
  useEffect(() => {
    const c = h.current, d = dataRef.current;
    if (!c || !d?.length || first == null || last == null) return;
    for (const s of c.segs) c.chart.removeSeries(s);
    c.segs = [];
    for (const sg of segments) {
      const a = barOf(d, Math.max(sg.t1, first)), b = barOf(d, sg.extend ? last : Math.min(sg.t2, last));
      if (a == null || b == null || a >= b || sg.t2 === sg.t1) continue;
      const at = (x: number) => sg.p1 + ((sg.p2 - sg.p1) * (x - sg.t1)) / (sg.t2 - sg.t1);
      const s = c.chart.addSeries(LineSeries, { color: sg.color, lineWidth: sg.width ?? 2, lineStyle: STYLES[sg.style ?? "dashed"], priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, autoscaleInfoProvider: () => null });
      s.setData([{ time: a as UTCTimestamp, value: at(a) }, { time: b as UTCTimestamp, value: at(b) }]);
      c.segs.push(s);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(segments), first, last, built]);

  // trade markers
  useEffect(() => {
    const c = h.current, d = dataRef.current;
    if (!c || !d?.length) return;
    c.marks.setMarkers(markers
      .flatMap((m) => { const bt = barOf(d, m.time); return bt == null ? [] : [{ time: bt as UTCTimestamp, position: m.position, shape: m.shape, color: m.color, text: m.text }]; })
      .sort((a, b) => a.time - b.time));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(markers), first, built]);

  // time window buttons and the fit button
  useEffect(() => { if (range) { want.current = range; applyWant(); } }, [range?.n]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (fit) fitAll(); }, [fit]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="relative h-full w-full">
      {err && <p className="absolute inset-0 z-10 grid place-items-center text-sm text-dim">Couldn't load candles: {err}</p>}
      {!data && !err && <Skeleton className="absolute inset-0 rounded-none" />}
      <div ref={box} className={"absolute inset-0 " + (drawing ? "cursor-crosshair" : "")} />
      <canvas ref={paint} className="pointer-events-none absolute inset-0 h-full w-full" />
    </div>
  );
}
