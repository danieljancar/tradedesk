import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { Box } from "@/components/shell";
import { api, useInterval } from "@/lib/api";
import { pc, px } from "@/lib/learn";
import { cn } from "@/lib/utils";

type Coin = { symbol: string; name: string; rank: number | null; price: number | null; change_24h: number | null; volume: number | null; on_binance: boolean; url: string };

export function Trending() {
  const [rows, setRows] = useState<Coin[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api<Coin[]>("/api/trending").then((r) => { setRows(r); setError(null); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  useInterval(load, 600_000);

  return (
    <Box title="Most searched on CoinGecko" pad={false} right={<span className="text-xs text-dim">watch only</span>}>
      {error && !rows && <p className="p-4 text-sm text-down">{error}</p>}
      {!rows && !error && <div className="m-4 h-24 animate-pulse rounded-md bg-sunk" />}
      {rows && (
        <ul className="divide-y divide-line/60">
          {rows.slice(0, 10).map((c) => (
            <li key={c.url}>
              <a href={c.url} target="_blank" rel="noreferrer" className="group flex items-center gap-3 px-4 py-2 hover:bg-raised/40">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px]"><b>{c.symbol}</b> <span className="text-dim">{c.name}</span></span>
                  <span className="block text-[11px] text-dim">{c.rank ? `rank ${c.rank}` : "unranked"}{c.on_binance ? ", on Binance" : ", not on Binance"}</span>
                </span>
                <span className="text-right">
                  <span className="block font-mono text-[12px] tabular-nums">{c.price != null ? px(c.price) : "–"}</span>
                  <span className={cn("block font-mono text-[11px] tabular-nums", c.change_24h != null && (c.change_24h >= 0 ? "text-up" : "text-down"))}>{c.change_24h != null ? pc(c.change_24h, 1) : ""}</span>
                </span>
                <ExternalLink className="size-3.5 shrink-0 text-dim opacity-0 group-hover:opacity-100" />
              </a>
            </li>
          ))}
        </ul>
      )}
      <p className="border-t border-line px-4 py-2 text-xs text-dim">What people search for in the last 24 hours. The desk doesn't trade from this list.</p>
    </Box>
  );
}
