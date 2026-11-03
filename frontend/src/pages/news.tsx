import { useMemo, useState } from "react";
import { ExternalLink, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Box, Page } from "@/components/shell";
import { useDeskCtx, type Headline } from "@/lib/desk-context";
import { cn } from "@/lib/utils";

const CATS = [["all", "Everything"], ["crypto", "Crypto"], ["markets", "Markets & economy"], ["world", "World"], ["politics", "Politics"]] as const;
const STOP = new Set("The A An And Or Of In On At To For With From By As Is Are Was Were Be Has Have Had It Its This That These Those After Before Over Under Into New Says Say Said How Why What Who When Will Could Would Should May Might Not No Than More Most Up Down Out About Amid Against Your You We Our Their They He She His Her Just Now Here Live Updates Week Day Year Today First Last Big South North East West".split(" "));
const MOVERS = /\b(fed|fomc|powell|rate|rates|inflation|cpi|jobs|payrolls|tariff|sec|etf|stablecoin|recession|treasury|yield|dollar|hack|exploit|liquidat\w*|bitcoin|ether(eum)?|binance)\b/i;

function ago(ts: number) {
  const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
  return m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
}

function trending(items: Headline[]) {
  const count = new Map<string, number>();
  for (const h of items.filter((h) => Date.now() / 1000 - h.ts < 12 * 3600)) {
    const words = new Set(h.title.replace(/[‘’'"“”:,.!?()]/g, " ").split(/\s+/).filter((w) => /^[A-Z][A-Za-z$&-]{2,}$/.test(w) && !STOP.has(w)));
    for (const w of words) count.set(w, (count.get(w) ?? 0) + 1);
  }
  return [...count].filter(([, n]) => n >= 3).sort((a, b) => b[1] - a[1]).slice(0, 12);
}

const SOURCES: [string, [string, string][]][] = [
  ["Charts and derivatives", [["TradingView", "https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT"], ["Binance", "https://www.binance.com/en/futures/BTCUSDT"], ["CoinGlass: funding, open interest, liquidations", "https://www.coinglass.com/"], ["CoinGecko", "https://www.coingecko.com/"]]],
  ["Macro calendar", [["Economic calendar (Investing.com)", "https://www.investing.com/economic-calendar/"], ["FOMC meeting dates", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"], ["CME FedWatch: rate odds", "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"], ["FRED economic data", "https://fred.stlouisfed.org/"]]],
  ["Flows and on-chain", [["Bitcoin ETF flows (Farside)", "https://farside.co.uk/btc/"], ["DefiLlama: stablecoins and TVL", "https://defillama.com/stablecoins"], ["Fear & Greed index", "https://alternative.me/crypto/fear-and-greed-index/"]]],
];

export default function News() {
  const d = useDeskCtx();
  const [cat, setCat] = useState<string>("all");
  const [q, setQ] = useState("");
  const [onlyMovers, setOnlyMovers] = useState(false);
  const top = useMemo(() => trending(d.news), [d.news]);
  const shown = d.news.filter((h) =>
    (cat === "all" || h.category === cat) &&
    (!q || h.title.toLowerCase().includes(q.toLowerCase())) &&
    (!onlyMovers || MOVERS.test(h.title)));

  return (
    <Page>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-56 flex-1">
              <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-dim" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search headlines" className="h-9 pl-8" aria-label="Search headlines" />
            </div>
            <div className="flex flex-wrap gap-1 rounded-lg bg-sunk p-1">
              {CATS.map(([v, label]) => (
                <button key={v} type="button" onClick={() => setCat(v)} aria-pressed={cat === v}
                  className={cn("rounded-md px-3 py-1 text-[13px] font-medium", cat === v ? "bg-panel text-fg shadow-sm" : "text-dim hover:text-fg")}>{label}</button>
              ))}
            </div>
            <button type="button" onClick={() => setOnlyMovers(!onlyMovers)} aria-pressed={onlyMovers}
              className={cn("rounded-md border px-3 py-1.5 text-[13px] font-medium", onlyMovers ? "border-brand bg-brand-soft text-brand-strong" : "border-line text-dim hover:text-fg")}>
              Market movers only
            </button>
          </div>

          {top.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-xs text-dim">Trending in the last 12 hours</span>
              {top.map(([w, n]) => (
                <button key={w} type="button" onClick={() => setQ(q === w ? "" : w)} aria-pressed={q === w}
                  className={cn("rounded-full px-2.5 py-0.5 text-xs", q === w ? "bg-brand text-brand-fg" : "bg-raised hover:bg-sunk")}>
                  {w} <span className="opacity-60">{n}</span>
                </button>
              ))}
            </div>
          )}

          <Box pad={false}>
            <ul className="divide-y divide-line/60">
              {shown.slice(0, 150).map((h) => {
                const mover = MOVERS.test(h.title);
                return (
                  <li key={h.link}>
                    <a href={h.link} target="_blank" rel="noreferrer" className="group flex items-start gap-4 px-4 py-3 hover:bg-raised/40">
                      <span className="w-16 shrink-0 pt-0.5 text-right font-mono text-[11px] text-dim">{ago(h.ts)}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-[14px] leading-snug group-hover:text-brand-strong">{h.title}</span>
                        <span className="mt-1 flex items-center gap-2 text-xs text-dim">
                          {h.source}
                          <span className="rounded bg-sunk px-1.5 py-px capitalize">{h.category}</span>
                          {mover && <span className="rounded bg-warn/12 px-1.5 py-px text-warn">can move prices</span>}
                        </span>
                      </span>
                      <ExternalLink className="mt-1 size-3.5 shrink-0 text-dim opacity-0 group-hover:opacity-100" />
                    </a>
                  </li>
                );
              })}
              {!shown.length && <li className="p-8 text-center text-sm text-dim">{d.news.length ? "Nothing matches." : "Loading headlines from 14 sources…"}</li>}
            </ul>
          </Box>
        </div>

        <div className="space-y-4">
          <Box title="Where the numbers come from">
            <div className="space-y-4">
              {SOURCES.map(([group, links]) => (
                <div key={group}>
                  <p className="mb-1.5 text-xs font-medium text-dim">{group}</p>
                  <ul className="space-y-0.5">
                    {links.map(([name, url]) => (
                      <li key={url}><a href={url} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[13px] hover:bg-raised">{name}<ExternalLink className="size-3.5 shrink-0 text-dim" /></a></li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Box>
          <Box title="Feeds">
            <p className="text-[13px] leading-relaxed text-dim">CoinDesk, Cointelegraph, Decrypt and The Block for crypto. CNBC, MarketWatch, the New York Times and BBC for markets. BBC, the Guardian and Al Jazeera for world news. Politico and the New York Times for politics. Refreshed every few minutes.</p>
          </Box>
        </div>
      </div>
    </Page>
  );
}
