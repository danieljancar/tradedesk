import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, LineStyle, createChart, createSeriesMarkers,
  type IChartApi, type ISeriesApi, type SeriesMarker, type UTCTimestamp,
} from "lightweight-charts";
import { api, type Candle } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

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
export type LineSpec = { price: number; title: string; color: string; style?: "solid" | "dashed" | "dotted"; width?: 1 | 2 | 3 };
export type MarkerSpec = { time: number; text: string; color: string; position: "aboveBar" | "belowBar"; shape: "arrowUp" | "arrowDown" | "circle" };

export function MarketChart({ asset, tf, overlay, lines, markers, drawing, onPick, onHover }: {
  asset: string; tf: string; overlay: Overlay; lines: LineSpec[]; markers: MarkerSpec[];
  drawing: boolean; onPick: (price: number) => void; onHover?: (c: Candle | null) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const drawRef = useRef(drawing);
  drawRef.current = drawing;
  const [data, setData] = useState<Candle[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scheme, setScheme] = useState(0);

  useEffect(() => {
    const mo = new MutationObserver(() => setScheme((x) => x + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    let alive = true;
    setData(null);
    setErr(null);
    const limit = tf === "1h" ? 400 : tf === "4h" ? 400 : tf === "1d" ? 365 : 200;
    api<Candle[]>(`/api/candles/${asset}?tf=${tf}&limit=${limit}`).then((d) => alive && setData(d)).catch((e) => alive && setErr(e.message));
    const t = setInterval(() => api<Candle[]>(`/api/candles/${asset}?tf=${tf}&limit=${limit}`).then((d) => alive && setData(d)).catch(() => {}), 60_000);
    return () => { alive = false; clearInterval(t); };
  }, [asset, tf]);

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
    if (overlay.volume) {
      const vol = chart.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
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
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, tf, overlay.ema, overlay.volume, JSON.stringify(lines), JSON.stringify(markers), scheme]);

  if (err) return <p className="grid h-full place-items-center text-sm text-dim">Couldn't load candles: {err}</p>;
  return (
    <div className="relative h-full w-full">
      {!data && <Skeleton className="absolute inset-0 rounded-none" />}
      <div ref={box} className={"absolute inset-0 " + (drawing ? "cursor-crosshair" : "")} />
    </div>
  );
}
