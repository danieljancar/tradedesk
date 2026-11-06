import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowLeft } from "lucide-react";
import { useDeskCtx } from "@/lib/desk-context";
import { Box } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import { pc, px } from "@/lib/learn";
import { useApi } from "@/lib/query";
import { cn } from "@/lib/utils";
import { squarify, type Rect } from "@/lib/treemap";

type Period = "1d" | "1w" | "1m";
type Tile = { symbol: string; name: string; sector: string; price: number; currency: string | null; cap: number | null } & Record<Period, number | null>;
type Board = { groups: { name: string; tiles: Tile[] }[]; as_of: number };

const PERIODS: { key: Period; label: string; full: number }[] = [
  { key: "1d", label: "1D", full: 3 },
  { key: "1w", label: "1W", full: 8 },
  { key: "1m", label: "1M", full: 15 },
];

// colour strength grows with the move, full at `full` percent
function shade(v: number | null, full: number) {
  if (v == null) return { background: "var(--t-sunk)" };
  const a = Math.min(Math.abs(v) / full, 1) * 0.75 + 0.08;
  return { background: `color-mix(in oklab, var(${v >= 0 ? "--up" : "--down"}) ${Math.round(a * 100)}%, var(--t-panel))` };
}

export function Heatmap() {
  const [period, setPeriod] = useState<Period>("1d");
  const { data, error } = useApi<Board>("/api/heatmap", { every: 60_000, stale: 50_000 });
  const [zoom, setZoom] = useState<string | null>(null);
  const p = PERIODS.find((x) => x.key === period)!;
  return (
    <Box title="Heatmap" pad={false} right={
      <div className="flex items-center gap-2">
      {zoom && <button type="button" onClick={() => setZoom(null)} className="flex items-center gap-1 text-xs text-dim hover:text-fg"><ArrowLeft className="size-3" />All groups</button>}
      <div className="flex rounded-md bg-sunk p-0.5">
        {PERIODS.map((x) => (
          <button key={x.key} type="button" onClick={() => setPeriod(x.key)} aria-pressed={period === x.key}
            className={cn("h-6 rounded-[5px] px-2.5 text-xs font-medium", period === x.key ? "bg-raised text-fg shadow-sm" : "text-dim hover:text-fg")}>{x.label}</button>
        ))}
      </div>
      </div>
    }>
      {error && !data && <p className="p-4 text-sm text-down">Couldn't load the heatmap: {error.message}</p>}
      {!data && !error && <div className="grid grid-cols-4 gap-1 p-3 sm:grid-cols-8">{Array.from({ length: 24 }, (_, i) => <Skeleton key={i} className="h-14 bg-sunk" />)}</div>}
      {data && <TreeMap board={zoom ? { ...data, groups: data.groups.filter((g) => g.name === zoom) } : data} period={period} full={p.full} onGroup={setZoom} />}
    </Box>
  );
}

const HEAD = 18;

/** Tile area from market cap (or fund assets), squashed a little so small names stay readable.
 * Without a size the tile gets the group's median. */
function weights(tiles: Tile[]) {
  const known = tiles.map((t) => t.cap).filter((c): c is number => !!c).sort((a, b) => a - b);
  const mid = known.length ? known[Math.floor(known.length / 2)] : 1;
  return tiles.map((t) => Math.pow(t.cap || mid, 0.75));
}

// heatmap tiles that have a chart on the markets page
const CHART: Record<string, string> = { "^GSPC": "SPX" };

function TreeMap({ board, period, full, onGroup }: { board: Board; period: Period; full: number; onGroup: (g: string) => void }) {
  const nav = useNavigate();
  const d = useDeskCtx();
  const target = (symbol: string) => {
    if (CHART[symbol]) return CHART[symbol];
    const coin = symbol.endsWith("-USD") ? symbol.slice(0, -4) : null;
    return coin && d.watch.includes(coin) ? coin : null;
  };
  const el = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!el.current) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el.current);
    return () => ro.disconnect();
  }, []);
  const groups = board.groups.filter((g) => g.tiles.length);
  const h = w < 640 ? 1100 : Math.round(Math.min(Math.max(w * 0.62, 520), 760));
  const outer = w ? squarify(groups.map((g) => g.tiles.length), { x: 0, y: 0, w, h }) : [];
  return (
    <div className="p-3">
      <div ref={el} className="relative w-full overflow-hidden rounded-md bg-line" style={{ height: h }}>
        {outer.map((r, gi) => {
          const g = groups[gi];
          const inner = squarify(weights(g.tiles), { x: r.x + 1, y: r.y + HEAD, w: r.w - 2, h: r.h - HEAD - 1 });
          return (
            <div key={g.name}>
              <button type="button" onClick={() => onGroup(g.name)} className="absolute truncate px-1.5 text-left text-[10px] leading-[18px] font-semibold tracking-[0.08em] text-dim uppercase hover:text-fg" style={{ left: r.x, top: r.y, width: r.w }}>{g.name}</button>
              {inner.map((t, i) => {
                const to = target(g.tiles[i].symbol);
                return <Cell key={g.tiles[i].symbol} tile={g.tiles[i]} r={t} period={period} full={full} onOpen={to ? () => nav(`/markets/${to}`) : undefined} />;
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Cell({ tile, r, period, full, onOpen }: { tile: Tile; r: Rect; period: Period; full: number; onOpen?: () => void }) {
  const v = tile[period];
  const big = Math.min(r.w, r.h * 2.2);
  const size = big > 160 ? 15 : big > 90 ? 13 : 11;
  return (
    <div title={`${tile.name}, ${px(tile.price)} ${tile.currency ?? ""}${v == null ? "" : `, ${pc(v, 2)}`}`} onClick={onOpen}
      className={cn("absolute flex flex-col items-center justify-center overflow-hidden border border-[var(--t-line)] text-center text-fg", onOpen && "cursor-pointer hover:brightness-125")}
      style={{ left: r.x, top: r.y, width: r.w, height: r.h, ...shade(v, full) }}>
      {r.w > 44 && r.h > 26 && <span className="max-w-full truncate px-1 font-medium" style={{ fontSize: size }}>{tile.name}</span>}
      {r.w > 34 && r.h > 16 && <span className="font-mono tabular-nums" style={{ fontSize: size - 1 }}>{v == null ? "–" : pc(v, 1)}</span>}
    </div>
  );
}
