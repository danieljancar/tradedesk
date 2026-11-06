import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, LineStyle, createChart, createSeriesMarkers,
  type IChartApi, type ISeriesApi, type SeriesMarker, type UTCTimestamp,
} from "lightweight-charts";
import { type Candle } from "@/lib/api";
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
export type MarkerSpec = { time: number; text: string; color: string; position: "aboveBar" | "belowBar"; shape: "arrowUp" | "arrowDown" | "circle" };

export function MarketChart({ asset, tf, overlay, lines, markers, segments = [], boxes = [], drawing, onPick, onHover }: {
  asset: string; tf: string; overlay: Overlay; lines: LineSpec[]; markers: MarkerSpec[]; segments?: SegmentSpec[]; boxes?: BoxSpec[];
  drawing: boolean; onPick: (price: number) => void; onHover?: (c: Candle | null) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const paint = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const drawRef = useRef(drawing);
  drawRef.current = drawing;
  const limit = tf === "1h" || tf === "4h" ? 400 : tf === "1d" ? 365 : 500;
  const candles = useApi<Candle[]>(`/api/candles/${asset}?tf=${tf}&limit=${limit}`, { every: 60_000 });
  const data = candles.data ?? null;
  const err = candles.data ? null : (candles.error?.message ?? null);
  const [scheme, setScheme] = useState(0);

  useEffect(() => {
    const mo = new MutationObserver(() => setScheme((x) => x + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    if (!data || !box.current) return;
    const up = cssColor("--up"), down = cssColor("--down"), fg = cssColor("--t-dim"), grid = cssColor("--t-line");
    const chart = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: fg, fontFamily: "Geist Variable, sans-serif", fontSize: 11, attributionLogo: false },
      grid: { vertLines: { color: cssColor("--t-line", 0.5) }, horzLines: { color: cssColor("--t-line", 0.5) } },
      rightPriceScale: { borderColor: grid, scaleMargins: { top: 0.06, bottom: overlay.volume ? 0.2 : 0.06 } },
      timeScale: { borderColor: grid, timeVisible: tf === "1h" || tf === "4h", rightOffset: 6 },
      crosshair: { mode: CrosshairMode.Normal },
    });
    chartRef.current = chart;
    const t = (c: Candle) => c.time as UTCTimestamp;
    const candles = chart.addSeries(CandlestickSeries, { upColor: up, downColor: down, borderVisible: false, wickUpColor: up, wickDownColor: down });
    seriesRef.current = candles;
    candles.setData(data.map((c) => ({ time: t(c), open: c.open, high: c.high, low: c.low, close: c.close })));
    let vol: ISeriesApi<"Histogram"> | null = null;
    if (overlay.volume) {
      vol = chart.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
      const us = cssColor("--up", 0.35), ds = cssColor("--down", 0.35);
      vol.setData(data.map((c) => ({ time: t(c), value: c.volume, color: c.close >= c.open ? us : ds })));
    }
    if (overlay.ema) {
      const closes = data.map((c) => c.close);
      for (const [p, color] of [[20, cssColor("--ema20")], [50, cssColor("--ema50")], [200, cssColor("--ema200")]] as const) {
        const e = ema(closes, p);
        if (e.every((x) => x == null)) continue;
        chart.addSeries(LineSeries, { color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
          .setData(data.flatMap((c, i) => (e[i] == null ? [] : [{ time: t(c), value: e[i]! }])));
      }
    }
    const styles = { solid: LineStyle.Solid, dashed: LineStyle.Dashed, dotted: LineStyle.Dotted };
    for (const l of lines) {
      candles.createPriceLine({ price: l.price, color: l.color, lineWidth: l.width ?? 1, lineStyle: styles[l.style ?? "dashed"], axisLabelVisible: true, title: l.title });
    }
    // a marker sits on the candle its event happened in
    const barOf = (ts: number) => {
      let lo = 0, hi = data.length - 1;
      if (ts < data[0].time) return null;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (data[mid].time <= ts) lo = mid; else hi = mid - 1; }
      return data[lo].time;
    };
    const ms: SeriesMarker<UTCTimestamp>[] = markers
      .flatMap((m) => { const bt = barOf(m.time); return bt == null ? [] : [{ time: bt as UTCTimestamp, position: m.position, shape: m.shape, color: m.color, text: m.text }]; })
      .sort((a, b) => a.time - b.time);
    if (ms.length) createSeriesMarkers(candles, ms);
    // a trendline from a longer timeframe gets cut to the bars on screen and, if asked, runs on to the last bar
    const first = data[0].time, last = data[data.length - 1].time;
    for (const sg of segments) {
      const from = Math.max(sg.t1, first), to = sg.extend ? last : Math.min(sg.t2, last);
      const a = barOf(from), b = barOf(to);
      if (a == null || b == null || a >= b || sg.t2 === sg.t1) continue;
      const at = (ts: number) => sg.p1 + ((sg.p2 - sg.p1) * (ts - sg.t1)) / (sg.t2 - sg.t1);
      chart.addSeries(LineSeries, { color: sg.color, lineWidth: sg.width ?? 2, lineStyle: styles[sg.style ?? "dashed"], priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
        .setData([{ time: a as UTCTimestamp, value: at(a) }, { time: b as UTCTimestamp, value: at(b) }]);
    }
    // plan and position zones, drawn on a canvas over the chart: green to the target, red to the stop
    let frame = 0;
    const draw = () => {
      const cv = paint.current, el = box.current;
      if (cv && el) {
        const w = el.clientWidth, h = el.clientHeight, dpr = devicePixelRatio || 1;
        if (cv.width !== w * dpr || cv.height !== h * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
        const g = cv.getContext("2d")!;
        g.setTransform(dpr, 0, 0, dpr, 0, 0);
        g.clearRect(0, 0, w, h);
        const right = w - (chart.priceScale("right").width() || 0);
        for (const bx of boxes) {
          const t = barOf(bx.from) ?? data[0].time;
          const x = chart.timeScale().timeToCoordinate(t as UTCTimestamp) ?? 0;
          const ye = candles.priceToCoordinate(bx.entry), ys = candles.priceToCoordinate(bx.stop), yt = candles.priceToCoordinate(bx.target);
          if (ye == null || ys == null || yt == null || x >= right) continue;
          g.fillStyle = bx.up; g.fillRect(x, Math.min(ye, yt), right - x, Math.abs(yt - ye));
          g.fillStyle = bx.down; g.fillRect(x, Math.min(ye, ys), right - x, Math.abs(ys - ye));
        }
      }
      frame = requestAnimationFrame(draw);
    };
    if (boxes.length) frame = requestAnimationFrame(draw);
    chart.subscribeClick((param) => {
      if (!drawRef.current || !param.point) return;
      const price = candles.coordinateToPrice(param.point.y);
      if (price != null) pickRef.current(Number(price));
    });
    if (onHover) {
      chart.subscribeCrosshairMove((param) => {
        if (!param.time) return onHover(null);
        const c = data.find((x) => x.time === param.time);
        onHover(c ?? null);
      });
    }
    const span = tf === "1w" ? 120 : tf === "1d" ? 150 : 180;
    chart.timeScale().setVisibleLogicalRange({ from: data.length - span, to: data.length + 5 });
    // the forming candle ticks live from Binance's public stream; the 60s refetch fills any gap
    const us = cssColor("--up", 0.35), ds = cssColor("--down", 0.35);
    const ws = new WebSocket(`wss://stream.binance.com:9443/ws/${asset.toLowerCase()}usdt@kline_${tf}`);
    ws.onmessage = (ev) => {
      const k = JSON.parse(ev.data)?.k;
      if (!k) return;
      const time = Math.floor(k.t / 1000) as UTCTimestamp;
      if (time < (data.at(-1)?.time ?? 0)) return;
      const bar = { time, open: +k.o, high: +k.h, low: +k.l, close: +k.c };
      candles.update(bar);
      vol?.update({ time, value: +k.v, color: bar.close >= bar.open ? us : ds });
    };
    return () => { cancelAnimationFrame(frame); paint.current?.getContext("2d")?.clearRect(0, 0, 1e5, 1e5); ws.close(); chart.remove(); chartRef.current = null; seriesRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, tf, overlay.ema, overlay.volume, JSON.stringify(lines), JSON.stringify(markers), JSON.stringify(segments), JSON.stringify(boxes), scheme]);

  if (err) return <p className="grid h-full place-items-center text-sm text-dim">Couldn't load candles: {err}</p>;
  return (
    <div className="relative h-full w-full">
      {!data && <Skeleton className="absolute inset-0 rounded-none" />}
      <div ref={box} className={"absolute inset-0 " + (drawing ? "cursor-crosshair" : "")} />
      <canvas ref={paint} className="pointer-events-none absolute inset-0 h-full w-full" />
    </div>
  );
}
