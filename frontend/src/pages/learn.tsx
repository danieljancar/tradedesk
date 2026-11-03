import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Box, Page } from "@/components/shell";
import { GLOSSARY } from "@/lib/learn";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

function StatTable({ title, rows }: { title: string; rows: any[] }) {
  if (!rows?.length) return null;
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-dim">{title}</p>
      <table className="w-full text-[13px]">
        <thead><tr className="text-left text-xs text-dim"><th className="py-1 font-medium">Group</th><th className="py-1 text-right font-medium">Ideas</th><th className="py-1 text-right font-medium">Hit rate</th><th className="py-1 text-right font-medium">Avg R</th></tr></thead>
        <tbody className="divide-y divide-line/60">
          {rows.map((r, i) => (
            <tr key={i} className={cn((r.n ?? 0) < 10 && "text-dim")}>
              <td className="py-1.5">{r.group ?? r.key ?? r.label ?? "–"}</td>
              <td className="py-1.5 text-right font-mono">{r.n ?? "–"}</td>
              <td className="py-1.5 text-right font-mono">{r.hit_rate != null ? `${Math.round(r.hit_rate * (r.hit_rate <= 1 ? 100 : 1))}%` : "–"}</td>
              <td className={cn("py-1.5 text-right font-mono", (r.avg_r ?? 0) >= 0 ? "text-up" : "text-down")}>{r.avg_r != null ? Number(r.avg_r).toFixed(2) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Learn() {
  const [q, setQ] = useState("");
  const [stats, setStats] = useState<any>(undefined);
  useEffect(() => { api<any>("/api/learning").then(setStats).catch(() => setStats(null)); }, []);
  const items = useMemo(() => Object.entries(GLOSSARY).sort((a, b) => a[1].term.localeCompare(b[1].term)), []);
  const shown = items.filter(([, g]) => !q || `${g.term} ${g.short} ${g.long ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  const tables = stats && typeof stats === "object"
    ? Object.entries(stats).filter(([, v]) => Array.isArray(v) && (v as any[]).length && typeof (v as any[])[0] === "object") as [string, any[]][]
    : [];

  return (
    <Page>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_440px]">
        <Box title="The words the desk uses" right={<span className="text-xs text-dim">{items.length} terms</span>}>
          <div className="relative mb-3">
            <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-dim" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search, e.g. RSI, funding, stop" className="h-9 pl-8" aria-label="Search the glossary" />
          </div>
          <dl className="grid gap-3 md:grid-cols-2">
            {shown.map(([k, g]) => (
              <div key={k} id={k} className="rounded-lg border border-line p-3">
                <dt className="font-semibold">{g.term}</dt>
                <dd className="mt-1 text-[13px] leading-relaxed">{g.short}</dd>
                {g.long && <dd className="mt-1 text-[13px] leading-relaxed text-dim">{g.long}</dd>}
              </div>
            ))}
          </dl>
        </Box>
        <div className="space-y-4">
          <Box title="What the desk has learned">
            {stats === undefined && <p className="text-sm text-dim">Loading…</p>}
            {stats === null && (
              <p className="text-[13px] leading-relaxed text-dim">
                Not enough history yet. Every idea the desk has, taken or not, gets replayed on real candles once it resolves.
                After about ten resolved ideas per group, this shows which confidence levels, coins and sides actually work, and the weekly review turns that into lessons the desk reads before every decision.
              </p>
            )}
            {tables.length > 0 && <div className="space-y-4">{tables.map(([k, rows]) => <StatTable key={k} title={k.replace(/_/g, " ")} rows={rows} />)}</div>}
            {stats && !tables.length && <pre className="max-h-96 overflow-auto rounded-md bg-sunk p-3 text-xs">{JSON.stringify(stats, null, 2)}</pre>}
          </Box>
          <Box title="How a run works">
            <ol className="list-decimal space-y-1.5 pl-5 text-[13px] leading-relaxed">
              <li>Prices, headlines and the account book are collected.</li>
              <li>A chart analyst and a news analyst write their reads.</li>
              <li>A bull and a bear argue both sides, one round.</li>
              <li>The portfolio manager writes plans with entry, stop and target, or passes.</li>
              <li>Python risk rules size every plan and reject what breaks a rule.</li>
              <li>Approved plans go to the exchange with the stop attached.</li>
            </ol>
          </Box>
        </div>
      </div>
    </Page>
  );
}
