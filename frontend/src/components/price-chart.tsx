import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, LineStyle, createChart,
  type IChartApi, type UTCTimestamp,
} from "lightweight-charts";
import { api, type Candle } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

function ema(values: number[], period: number) {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let prev: number | null = null;
  values.forEach((v, i) => {
    if (i < period - 1) { out.push(null); return; }
    if (prev == null) prev = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
    else prev = v * k + prev * (1 - k);
    out.push(prev);
  });
  return out;
}

const ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true })!;

/** Lightweight Charts only understands hex/rgb, so resolve any CSS color (oklch included) through a canvas. */
function css(name: string, alpha = 1) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillStyle = "#000";
  ctx.fillStyle = raw;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
  return `rgba(${r}, ${g}, ${b}, ${((a / 255) * alpha).toFixed(3)})`;
}

export type Levels = { support: number[]; resistance: number[] };

export function PriceChart({ asset, tf, levels, height = 300 }: { asset: string; tf: string; levels?: Levels; height?: number }) {
  const box = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<Candle[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scheme, setScheme] = useState(() => document.documentElement.classList.contains("dark"));

  useEffect(() => {
    const mo = new MutationObserver(() => setScheme(document.documentElement.classList.contains("dark")));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    let alive = true;
    setData(null);
    setErr(null);
    api<Candle[]>(`/api/candles/${asset}?tf=${tf}&limit=${tf === "1w" ? 160 : 220}`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setErr(e.message));
    return () => { alive = false; };
  }, [asset, tf]);

  useEffect(() => {
    if (!data || !box.current) return;
    const up = css("--up"), down = css("--down"), fg = css("--muted-foreground"), grid = css("--border");
    const chart: IChartApi = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: fg, fontFamily: "Geist Variable, sans-serif", attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: grid, style: LineStyle.Dotted } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.22 } },
      timeScale: { borderVisible: false, timeVisible: tf === "4h", rightOffset: 4 },
      crosshair: { mode: CrosshairMode.Magnet },
      handleScroll: { mouseWheel: false, pressedMouseMove: true },
      handleScale: { mouseWheel: false, pinch: true },
    });
    const t = (c: Candle) => c.time as UTCTimestamp;
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: up, downColor: down, borderVisible: false, wickUpColor: up, wickDownColor: down,
      priceLineColor: fg,
    });
    candles.setData(data.map((c) => ({ time: t(c), open: c.open, high: c.high, low: c.low, close: c.close })));
    const vol = chart.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    const upSoft = css("--up", 0.33), downSoft = css("--down", 0.33);
    vol.setData(data.map((c) => ({ time: t(c), value: c.volume, color: c.close >= c.open ? upSoft : downSoft })));
    const closes = data.map((c) => c.close);
    for (const [p, color] of [[20, css("--ema20")], [50, css("--ema50")], [200, css("--ema200")]] as const) {
      const e = ema(closes, p);
      if (e.every((x) => x == null)) continue;
      const s = chart.addSeries(LineSeries, { color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      s.setData(data.flatMap((c, i) => (e[i] == null ? [] : [{ time: t(c), value: e[i]! }])));
    }
    const price = closes.at(-1)!;
    const near = (xs: number[], below: boolean) => xs.filter((x) => (below ? x < price : x > price)).sort((a, b) => (below ? b - a : a - b)).slice(0, 2);
    for (const lv of near(levels?.support ?? [], true)) {
      candles.createPriceLine({ price: lv, color: up, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "support" });
    }
    for (const lv of near(levels?.resistance ?? [], false)) {
      candles.createPriceLine({ price: lv, color: down, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "resistance" });
    }
    chart.timeScale().setVisibleLogicalRange({ from: data.length - (tf === "1w" ? 80 : 110), to: data.length + 3 });
    return () => chart.remove();
  }, [data, levels, tf, scheme]);

  if (err) return <p className="grid place-items-center text-sm text-muted-foreground" style={{ height }}>Couldn't load candles: {err}</p>;
  return (
    <div className="relative" style={{ height }}>
      {!data && <Skeleton className="absolute inset-0" />}
      <div ref={box} className="absolute inset-0" />
    </div>
  );
}
