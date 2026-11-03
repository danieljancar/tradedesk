import { useCallback, useEffect, useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AgentSheet, Glossary } from "@/components/panels";
import { AccountPanel, BottomTabs, DeskRail, Footer, MainPanel, NewsPanel, Signals, TopBar, useTickers } from "@/components/terminal";
import { TermLayer } from "@/components/term";
import { useDesk } from "@/lib/api";

function useTheme() {
  const read = () => { try { return localStorage.getItem("color-scheme"); } catch { return null; } };
  const [scheme, setScheme] = useState<string>(() => read() ?? "dark");
  const dark = scheme === "dark";
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); }, [dark]);
  const toggle = () => {
    const next = dark ? "light" : "dark";
    try { localStorage.setItem("color-scheme", next); } catch { /* storage blocked */ }
    setScheme(next);
  };
  return { dark, toggle };
}

export default function App() {
  const desk = useDesk();
  const { dark, toggle } = useTheme();
  const [agent, setAgent] = useState<string | null>(null);
  const [learn, setLearn] = useState(false);
  const pick = useCallback((id: string) => setAgent(id), []);
  const assets = desk.facts ? Object.keys(desk.facts).filter((k) => !k.startsWith("_")) : ["BTC", "ETH", "SOL"];
  const [asset, setAsset] = useState("BTC");
  useEffect(() => { if (assets.length && !assets.includes(asset)) setAsset(assets[0]); }, [assets.join()]); // eslint-disable-line react-hooks/exhaustive-deps
  const ticks = useTickers(assets);
  const run = desk.runs.find((r) => r.id === desk.runId);

  return (
    <TooltipProvider>
      <TermLayer>
        <div className="flex min-h-dvh flex-col bg-bg text-fg lg:h-dvh">
          <TopBar assets={assets} asset={asset} setAsset={setAsset} ticks={ticks} facts={desk.facts} state={desk.state}
            runs={desk.runs} runId={desk.runId} select={desk.select} dark={dark} toggle={toggle} onLearn={() => setLearn(true)} refresh={desk.refresh} />
          <div className="grid min-h-0 flex-1 gap-px bg-line lg:grid-cols-[minmax(0,1fr)_330px] lg:grid-rows-[minmax(0,1fr)_minmax(0,38%)]">
            <div className="h-[62vh] min-h-0 lg:h-auto">
              <MainPanel asset={asset} facts={desk.facts} run={run} events={desk.events} fresh={desk.fresh} onPick={pick} />
            </div>
            <div className="flex min-h-0 flex-col gap-px lg:row-span-2">
              <AccountPanel state={desk.state} />
              <Signals asset={asset} facts={desk.facts} />
              <div className="min-h-[300px] flex-1 basis-0 lg:min-h-0"><DeskRail events={desk.events} run={run} onPick={pick} /></div>
            </div>
            <div className="grid min-h-0 gap-px bg-line lg:col-start-1 lg:row-start-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="h-[320px] min-h-0 xl:h-auto"><BottomTabs state={desk.state} events={desk.events} refresh={desk.refresh} onPick={pick} /></div>
              <div className="h-[420px] min-h-0 xl:h-auto"><NewsPanel asset={asset} /></div>
            </div>
          </div>
          <Footer ticks={ticks} assets={assets} run={run} />
        </div>
        <AgentSheet id={agent} events={desk.events} onClose={() => setAgent(null)} />
        <Glossary open={learn} onOpenChange={setLearn} />
        <Toaster position="bottom-right" theme={dark ? "dark" : "light"} />
      </TermLayer>
    </TooltipProvider>
  );
}
