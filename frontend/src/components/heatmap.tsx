import { useState } from "react";
import { Box } from "@/components/shell";
import { Skeleton } from "@/components/ui/skeleton";
import { pc, px } from "@/lib/learn";
import { useApi } from "@/lib/query";
import { cn } from "@/lib/utils";

type Period = "1d" | "1w" | "1m";
type Tile = { symbol: string; name: string; sector: string; price: number; currency: string | null } & Record<Period, number | null>;
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
  const { data, error } = useApi<Board>("/api/heatmap", { every: 300_000, stale: 240_000 });
  const p = PERIODS.find((x) => x.key === period)!;
  return (
    <Box title="Heatmap" pad={false} right={
      <div className="flex rounded-md bg-sunk p-0.5">
        {PERIODS.map((x) => (
          <button key={x.key} type="button" onClick={() => setPeriod(x.key)} aria-pressed={period === x.key}
            className={cn("h-6 rounded-[5px] px-2.5 text-xs font-medium", period === x.key ? "bg-raised text-fg shadow-sm" : "text-dim hover:text-fg")}>{x.label}</button>
        ))}
      </div>
    }>
      {error && !data && <p className="p-4 text-sm text-down">Couldn't load the heatmap: {error.message}</p>}
      {!data && !error && <div className="grid grid-cols-4 gap-1 p-3 sm:grid-cols-8">{Array.from({ length: 24 }, (_, i) => <Skeleton key={i} className="h-14 bg-sunk" />)}</div>}
      {data && (
        <div className="space-y-3 p-3">
          {data.groups.filter((g) => g.tiles.length).map((g) => (
            <section key={g.name}>
              <h3 className="mb-1.5 text-[11px] font-semibold tracking-[0.08em] text-dim uppercase">{g.name}</h3>
              <ul className="grid grid-cols-[repeat(auto-fill,minmax(108px,1fr))] gap-1">
                {g.tiles.map((t) => (
                  <li key={t.symbol} style={shade(t[period], p.full)} title={`${t.name}, ${px(t.price)} ${t.currency ?? ""}`}
                    className="rounded-md px-2 py-1.5">
                    <p className="truncate text-[12px] font-medium text-fg">{t.name}</p>
                    <p className="font-mono text-[13px] tabular-nums text-fg">{t[period] == null ? "–" : pc(t[period]!, 2)}</p>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <p className="text-[11px] text-dim">Yahoo Finance, refreshed every 5 minutes. Stock markets move only in their trading hours, coins around the clock.</p>
        </div>
      )}
    </Box>
  );
}
