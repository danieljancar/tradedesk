import { useState } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight, ChevronDown } from "lucide-react";
import { PolarAngleAxis, RadialBar, RadialBarChart } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ChartContainer } from "@/components/ui/chart";
import { PriceChart } from "@/components/price-chart";
import { Term } from "@/components/term";
import { pc, px, readAsset, readMood } from "@/lib/learn";
import { cn } from "@/lib/utils";

const TF_HELP: Record<string, string> = {
  "4h": "Each candle is 4 hours. Shows the next few days.",
  "1d": "Each candle is one day. Shows the next few weeks.",
  "1w": "Each candle is one week. The big picture, months.",
};

function Dir({ dir }: { dir: string }) {
  const Icon = dir === "up" ? ArrowUpRight : dir === "down" ? ArrowDownRight : ArrowRight;
  return (
    <span className={cn("inline-flex items-center gap-1 font-medium", dir === "up" && "text-up", dir === "down" && "text-down", dir !== "up" && dir !== "down" && "text-muted-foreground")}>
      <Icon className="size-3.5" aria-hidden="true" />
      {dir === "up" ? "up" : dir === "down" ? "down" : "sideways"}
    </span>
  );
}

function Mood({ market }: { market: any }) {
  const m = readMood(market);
  if (!m) return null;
  const color = m.value < 25 ? "var(--down)" : m.value < 45 ? "var(--warn)" : m.value <= 55 ? "var(--muted-foreground)" : "var(--up)";
  return (
    <div className="grid gap-4 sm:grid-cols-[1.4fr_1fr]">
      <Card className="flex-row items-center gap-4 px-5 py-4">
        <ChartContainer config={{ v: { label: "Fear & Greed", color } }} className="aspect-square h-24 shrink-0">
          <RadialBarChart data={[{ v: m.value, fill: color }]} startAngle={210} endAngle={-30} innerRadius="78%" outerRadius="100%">
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar dataKey="v" background={{ fill: "var(--muted)" }} cornerRadius={10} />
            <text x="50%" y="52%" textAnchor="middle" dominantBaseline="middle" className="fill-foreground font-heading text-2xl font-semibold">{m.value}</text>
          </RadialBarChart>
        </ChartContainer>
        <div className="space-y-1">
          <p className="font-heading text-lg font-semibold">{m.label}</p>
          <p className="text-sm"><Term k="feargreed">Crowd mood</Term>: {m.text}</p>
          <div className="flex items-end gap-1 pt-1" aria-label={`Last 7 days, newest first: ${m.week.join(", ")}`}>
            {[...m.week].reverse().map((v, i) => (
              <span key={i} className="w-3 rounded-sm bg-muted-foreground/30" style={{ height: 4 + v / 4 }} title={String(v)} />
            ))}
            <span className="ml-2 text-xs text-muted-foreground">last 7 days</span>
          </div>
        </div>
      </Card>
      {market?.dominance && (
        <Card className="justify-center gap-1 px-5 py-4">
          <p className="font-heading text-2xl font-semibold tabular-nums">{market.dominance.BTC.toFixed(1)}%</p>
          <p className="text-sm">of all crypto value is bitcoin (<Term k="dominance">dominance</Term>).</p>
          <p className="text-xs text-muted-foreground">Whole market {pc(market.market_cap_change_24h)} in the last 24 hours</p>
        </Card>
      )}
    </div>
  );
}

function AssetCard({ asset, f }: { asset: string; f: any }) {
  const [tf, setTf] = useState("1d");
  const [open, setOpen] = useState(false);
  const r = readAsset(asset, f);
  const ch = f.change?.["1d"];
  const lo = r.levels.below, hi = r.levels.above;
  const k = lo != null && hi != null ? Math.max(0, Math.min(1, (f.price - lo) / (hi - lo))) : null;

  return (
    <Card className="gap-0 overflow-hidden py-0">
      <CardHeader className="flex flex-row items-start justify-between gap-4 border-b px-5 py-4">
        <div>
          <CardDescription className="font-mono text-xs tracking-wide">{f.symbol}</CardDescription>
          <CardTitle className="flex items-baseline gap-3 font-heading text-3xl tabular-nums">
            {px(f.price)}
            <span className={cn("text-sm font-medium", ch >= 0 ? "text-up" : "text-down")}>{pc(ch)} <span className="text-muted-foreground">24h</span></span>
          </CardTitle>
          <p className="mt-2 max-w-prose text-sm leading-relaxed">{r.headline}</p>
        </div>
        <Badge variant="secondary" className="shrink-0 font-heading text-base">{asset}</Badge>
      </CardHeader>

      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4">
        <Tabs value={tf} onValueChange={setTf}>
          <TabsList>
            {["4h", "1d", "1w"].map((x) => (
              <TabsTrigger key={x} value={x} className="gap-1.5 tabular-nums">
                {x} <Dir dir={r.trends[x].dir} />
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <p className="text-xs text-muted-foreground"><Term k="candle">{TF_HELP[tf]}</Term></p>
      </div>
      <div className="px-2 pt-2">
        <PriceChart asset={asset} tf={tf} levels={f.levels?.[tf === "1w" ? "1d" : tf]} />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 px-5 pb-3 text-xs text-muted-foreground">
        <span className="legend" style={{ ["--c" as any]: "var(--ema20)" }}><Term k="ema">ema20</Term> short trend</span>
        <span className="legend" style={{ ["--c" as any]: "var(--ema50)" }}>ema50 medium</span>
        <span className="legend" style={{ ["--c" as any]: "var(--ema200)" }}>ema200 long</span>
        <span className="legend dashed" style={{ ["--c" as any]: "var(--up)" }}><Term k="support" /></span>
        <span className="legend dashed" style={{ ["--c" as any]: "var(--down)" }}><Term k="resistance" /></span>
      </div>

      {k != null && (
        <div className="mx-5 mb-4 rounded-lg bg-muted/60 px-4 py-3">
          <div className="mb-2 flex justify-between text-xs">
            <span><Term k="support">Floor</Term> <b className="tabular-nums">{px(lo)}</b></span>
            <span className="text-muted-foreground">where price sits between them</span>
            <span><b className="tabular-nums">{px(hi)}</b> <Term k="resistance">ceiling</Term></span>
          </div>
          <div className="relative h-2 rounded-full bg-gradient-to-r from-up/60 via-muted-foreground/25 to-down/60" role="img" aria-label={`${Math.round(k * 100)}% of the way from floor to ceiling`}>
            <span className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground shadow" style={{ left: `${k * 100}%` }} />
          </div>
        </div>
      )}

      <CardContent className="border-t px-0">
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
          className="flex w-full items-center justify-between px-5 py-3 text-left text-sm font-medium hover:bg-muted/50">
          What every number means
          <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden="true" />
        </button>
        {open && (
          <dl className="divide-y border-t">
            {r.lines.map((l) => (
              <div key={l.key} className="grid gap-x-4 gap-y-1 px-5 py-3 sm:grid-cols-[10rem_8rem_1fr]">
                <dt className="text-sm"><Term k={l.term}>{l.label}</Term></dt>
                <dd className={cn("font-mono text-sm tabular-nums", l.tone === "up" && "text-up", l.tone === "down" && "text-down", l.tone === "warn" && "text-warn")}>{l.value}</dd>
                <dd className="text-sm leading-relaxed text-muted-foreground">{l.text}</dd>
              </div>
            ))}
          </dl>
        )}
        <div className="flex gap-4 border-t px-5 py-3 text-xs text-muted-foreground">
          {["7d", "30d", "90d"].map((x) => (
            <span key={x}>{x} <b className={cn("tabular-nums", f.change?.[x] >= 0 ? "text-up" : "text-down")}>{pc(f.change?.[x])}</b></span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function Market({ facts }: { facts: any }) {
  const assets = facts ? Object.keys(facts).filter((k) => !k.startsWith("_")) : [];
  if (!assets.length) return <p className="text-sm text-muted-foreground">No snapshot in this run yet.</p>;
  if (!facts[assets[0]].frames) {
    return <p className="text-sm text-muted-foreground">This run was made before the plain-language data existed. Pick a newer run or run the desk again.</p>;
  }
  return (
    <div className="space-y-4">
      <Mood market={facts._market} />
      {assets.map((a) => <AssetCard key={a} asset={a} f={facts[a]} />)}
    </div>
  );
}
