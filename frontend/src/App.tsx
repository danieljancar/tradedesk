import { useCallback, useEffect, useState } from "react";
import { BookOpen, Moon, RefreshCw, Sun } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Floor } from "@/components/floor";
import { Market } from "@/components/market";
import { Account, AgentSheet, Avatar, Call, Glossary, Plans, Talk } from "@/components/panels";
import { TermLayer } from "@/components/term";
import { api, useDesk } from "@/lib/api";
import { px } from "@/lib/learn";

const runLabel = (id: string) => {
  const d = new Date(id.replace(/T(\d\d)(\d\d)$/, "T$1:$2:00Z"));
  return Number.isNaN(+d) ? id : d.toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};

function useTheme() {
  const sys = matchMedia("(prefers-color-scheme: dark)");
  const read = () => { try { return localStorage.getItem("color-scheme"); } catch { return null; } };
  const [stored, setStored] = useState<string | null>(read);
  const [sysDark, setSysDark] = useState(sys.matches);
  useEffect(() => {
    const on = (e: MediaQueryListEvent) => setSysDark(e.matches);
    sys.addEventListener("change", on);
    return () => sys.removeEventListener("change", on);
  }, [sys]);
  const dark = stored ? stored === "dark" : sysDark;
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); }, [dark]);
  const toggle = () => {
    const target = dark ? "light" : "dark";
    const next = target === (sysDark ? "dark" : "light") ? null : target;
    try { if (next) localStorage.setItem("color-scheme", next); else localStorage.removeItem("color-scheme"); } catch { /* storage blocked */ }
    setStored(next);
  };
  return { dark, toggle };
}

function Section({ title, sub, children, id }: { title: string; sub?: string; children: React.ReactNode; id?: string }) {
  return (
    <section aria-labelledby={id} className="space-y-3">
      <div>
        <h2 id={id} className="font-heading text-xl font-semibold tracking-tight">{title}</h2>
        {sub && <p className="text-sm text-muted-foreground">{sub}</p>}
      </div>
      {children}
    </section>
  );
}

export default function App() {
  const desk = useDesk();
  const { dark, toggle } = useTheme();
  const [agent, setAgent] = useState<string | null>(null);
  const [learn, setLearn] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const pick = useCallback((id: string) => setAgent(id), []);
  const run = desk.runs.find((r) => r.id === desk.runId);
  const eq = desk.state?.equity.at(-1)?.value;

  const sync = async () => {
    setSyncing(true);
    try { await api("/api/sync", "POST"); toast.success("Synced with the exchange"); } catch (e: any) { toast.error(e.message); }
    setSyncing(false);
    desk.refresh();
  };

  return (
    <TooltipProvider>
      <TermLayer>
        <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5 sm:flex-nowrap sm:px-6">
            <Avatar id="bull" size={34} mood="awake" />
            <h1 className="font-heading text-lg font-bold tracking-tight">tradedesk</h1>
            {desk.state && (
              <Badge variant={desk.state.mode === "live" ? "destructive" : "secondary"} className="uppercase">
                {desk.state.mode} · {desk.state.market}
              </Badge>
            )}
            <div className="ml-auto hidden items-baseline gap-2 text-sm md:flex">
              <span className="text-muted-foreground">Account</span>
              <b className="tabular-nums">{eq == null ? "…" : `${px(eq)} ${desk.state?.quote}`}</b>
            </div>
            <Select value={desk.runId ?? undefined} onValueChange={desk.select}>
              <SelectTrigger className="order-last w-full sm:order-none sm:w-[13.5rem]" aria-label="Run"><SelectValue placeholder="Pick a run" /></SelectTrigger>
              <SelectContent>
                {desk.runs.map((r) => (
                  <SelectItem key={r.id} value={r.id}>{runLabel(r.id)}{r.status === "running" ? " · live" : ""}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="ghost" className="ml-auto sm:ml-0" onClick={() => setLearn(true)}><BookOpen /> <span className="hidden sm:inline">Learn</span></Button>
            <Button variant="ghost" size="icon" onClick={toggle} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}>{dark ? <Sun /> : <Moon />}</Button>
            <Button variant="outline" onClick={sync} disabled={syncing}><RefreshCw className={syncing ? "animate-spin" : ""} /> <span className="hidden sm:inline">Sync</span></Button>
          </div>
        </header>

        <main className="mx-auto grid max-w-[1400px] gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-w-0 space-y-8">
            <Card className="gap-4 overflow-hidden">
              <CardHeader>
                <CardTitle className="font-heading text-xl">Trading floor</CardTitle>
                <CardDescription>
                  {run ? (run.status === "running" ? "Live now. Watch them work." : `${runLabel(run.id)}${run.summary ? ` · ${run.summary.split("\n")[0]}` : ""}`) : "Waiting for a run"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Floor runId={desk.runId} finished={run?.status !== "running"} events={desk.events} fresh={desk.fresh} onPick={pick} />
                <p className="mt-3 text-xs text-muted-foreground">Move your mouse, they're watching. Click anyone to see what they do and read what they wrote.</p>
              </CardContent>
            </Card>

            <Call events={desk.events} />

            <Section id="plans-title" title="Trade plans" sub="Ideas from the last three days, in plain words.">
              <Plans state={desk.state} refresh={desk.refresh} />
            </Section>

            <Section id="market-title" title="The market, in plain words" sub="Real charts and every number from this run's snapshot. Tap any underlined word to learn it.">
              <Market facts={desk.facts} />
            </Section>

            <Section id="talk-title" title="How they got there" sub="The run as a conversation, in order.">
              <Talk events={desk.events} onPick={pick} />
            </Section>
          </div>
          <aside className="min-w-0 lg:sticky lg:top-20 lg:self-start">
            <Account state={desk.state} refresh={desk.refresh} />
          </aside>
        </main>

        <AgentSheet id={agent} events={desk.events} onClose={() => setAgent(null)} />
        <Glossary open={learn} onOpenChange={setLearn} />
        <Toaster position="bottom-center" />
      </TermLayer>
    </TooltipProvider>
  );
}
