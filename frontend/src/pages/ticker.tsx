import { useState } from "react";
import { Box, Page, PageSkeleton } from "@/components/shell";
import { Prose } from "@/components/prose";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeskCtx } from "@/lib/desk-context";
import { useApi } from "@/lib/query";
import { cn } from "@/lib/utils";

type Listing = { briefs: { date: string; headline: string }[]; calendar: string };

export default function Ticker() {
  const d = useDeskCtx();
  const { data, error } = useApi<Listing>("/api/ticker", { every: 300_000 });
  const [picked, setPicked] = useState<string | null>(null);
  const day = picked ?? data?.briefs[0]?.date ?? null;
  const brief = useApi<{ date: string; html: string }>(day ? `/api/ticker/${day}` : null, { stale: 600_000 });

  if (error && !data) return <Page><Box title="Handelsticker"><p className="text-sm text-down">Couldn't load the briefs: {error.message}</p></Box></Page>;
  if (!data) return <PageSkeleton />;

  return (
    <Page>
      <div className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)_320px]">
        <Box title="Briefs" pad={false} className="xl:self-start" right={
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => d.act("/api/ticker", "POST", "Writing today's brief, it takes a few minutes")}>Write now</Button>
        }>
          {data.briefs.length === 0 ? <p className="p-4 text-sm text-dim">No brief yet.</p> : (
            <ul className="max-h-[70vh] overflow-y-auto p-1.5">
              {data.briefs.map((b) => (
                <li key={b.date}>
                  <button type="button" onClick={() => setPicked(b.date)}
                    className={cn("w-full rounded-md px-2.5 py-2 text-left hover:bg-raised", b.date === day && "bg-raised")}>
                    <span className="block font-mono text-xs text-dim">{b.date}</span>
                    <span className="line-clamp-2 text-[13px]">{b.headline}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Box>
        <Box title={day ? `Handelsticker ${day}` : "Handelsticker"} fold="ticker.brief">
          {!day ? <p className="text-sm text-dim">The first brief comes with the next morning run.</p>
            : brief.data ? <Prose html={brief.data.html} />
              : <div className="space-y-2"><Skeleton className="h-5 w-2/3 bg-sunk" /><Skeleton className="h-40 bg-sunk" /></div>}
        </Box>
        <Box title="Calendar" className="xl:self-start">
          {data.calendar ? <Prose html={data.calendar} /> : <p className="text-sm text-dim">No events yet.</p>}
        </Box>
      </div>
    </Page>
  );
}
