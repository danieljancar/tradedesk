import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router";
import {
  ArrowLeftRight, BookOpen, CandlestickChart, LayoutDashboard, LineChart, Menu, Moon, Newspaper, Play, RefreshCw, Settings, Sun, Users, Wallet,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Avatar } from "@/components/panels";
import { useDeskCtx } from "@/lib/desk-context";
import { px } from "@/lib/learn";
import { cn } from "@/lib/utils";

export const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/portfolio", label: "Portfolio", icon: Wallet },
  { to: "/markets", label: "Markets", icon: CandlestickChart },
  { to: "/desk", label: "Desk", icon: Users },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/performance", label: "Performance", icon: LineChart },
  { to: "/news", label: "News", icon: Newspaper },
  { to: "/learn", label: "Learn", icon: BookOpen },
  { to: "/settings", label: "Settings", icon: Settings },
];

function useClock(iso?: string | null) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function Shell({ children, dark, toggle }: { children: ReactNode; dark: boolean; toggle: () => void }) {
  const d = useDeskCtx();
  const loc = useLocation();
  const [syncing, setSyncing] = useState(false);
  const [more, setMore] = useState(false);
  const latest = d.runs[0];
  const live = latest?.status === "running";
  const lastAt = useClock(latest?.started_at);
  const eq = d.state?.equity.at(-1)?.value;
  const first = d.state?.equity[0]?.value;
  const pnl = eq != null && first != null ? eq - first : 0;
  const waiting = d.state?.plans.filter((p) => p.status === "proposed").length ?? 0;
  const regime = d.macro?.regime;
  const title = NAV.find((n) => (n.end ? loc.pathname === n.to : loc.pathname.startsWith(n.to)))?.label ?? "";

  const sync = async () => { setSyncing(true); await d.act("/api/sync", "POST", "Synced with the exchange"); setSyncing(false); };

  return (
    <div className="flex h-dvh bg-bg text-fg">
      <aside className="hidden w-[208px] shrink-0 flex-col border-r border-line bg-panel md:flex">
        <div className="flex h-14 items-center gap-2.5 px-4">
          <Avatar id="bull" size={30} mood="awake" />
          <div>
            <p className="font-heading text-[15px] leading-none font-bold tracking-tight">tradedesk</p>
            <p className="mt-1 text-[10px] font-semibold tracking-wider text-dim uppercase">{d.state ? `${d.state.mode} ${d.state.market}` : ""}</p>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-2 py-2" aria-label="Pages">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-[13.5px] font-medium transition-colors",
              isActive ? "bg-brand-soft text-brand-strong" : "text-dim hover:bg-raised hover:text-fg")}>
              <Icon className="size-4" />
              <span className="flex-1">{label}</span>
              {label === "Trades" && waiting > 0 && <span className="rounded bg-brand px-1.5 text-[10px] font-bold text-brand-fg">{waiting}</span>}
              {label === "Desk" && live && <span className="size-1.5 animate-pulse rounded-full bg-up" />}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-2 border-t border-line p-3">
          <div className="rounded-md bg-sunk px-3 py-2">
            <p className="text-[11px] text-dim">Equity</p>
            <p className="font-mono text-lg leading-tight tabular-nums">{eq == null ? "–" : px(eq)} <span className="text-xs text-dim">{d.state?.quote}</span></p>
            <p className={cn("font-mono text-[11px] tabular-nums", pnl >= 0 ? "text-up" : "text-down")}>{pnl >= 0 ? "+" : "−"}{Math.abs(pnl).toFixed(2)} since start</p>
          </div>
          <p className="px-1 text-[11px] text-dim">{d.state?.auto_execute ? "Auto-execute on: passed plans trade without approval." : "Manual approval: you approve every trade."}</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line bg-panel px-3 sm:px-4">
          <div className="flex items-center gap-2 md:hidden"><Avatar id="bull" size={26} mood="awake" /></div>
          <h1 className="font-heading text-lg font-semibold tracking-tight">{title}</h1>
          {regime && (
            <NavLink to="/" className={cn("ml-2 hidden items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium sm:flex",
              regime.label === "Risk-on" ? "bg-up/12 text-up" : regime.label === "Risk-off" ? "bg-down/12 text-down" : "bg-warn/12 text-warn")}>
              Macro {regime.label.toLowerCase()} <span className="font-mono opacity-80">{regime.tailwinds}↑ {regime.headwinds}↓</span>
            </NavLink>
          )}
          <div className="ml-auto flex items-center gap-1.5">
            <NavLink to="/desk" className={cn("hidden items-center gap-1.5 rounded-md px-2 py-1 text-xs lg:flex", live ? "bg-up/12 text-up" : "bg-sunk text-dim")}>
              <span className={cn("size-1.5 rounded-full", live ? "animate-pulse bg-up" : "bg-dim/60")} />
              {live ? "Desk working" : latest ? `Idle, last run ${lastAt}` : "No runs yet"}
            </NavLink>
            <Button size="sm" onClick={d.runNow} disabled={live} className="h-8 gap-1.5">
              <Play className="size-3.5" /> <span className="hidden sm:inline">Run desk</span>
            </Button>
            <Button variant="ghost" size="icon" className="size-8" onClick={sync} disabled={syncing} aria-label="Sync with exchange">
              <RefreshCw className={cn("size-4", syncing && "animate-spin")} />
            </Button>
            <Button variant="ghost" size="icon" className="size-8" onClick={toggle} aria-label={dark ? "Light theme" : "Dark theme"}>
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto pb-16 md:pb-0">{children}</main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-panel/95 backdrop-blur md:hidden" aria-label="Pages">
        {NAV.slice(0, 5).map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => cn("flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px]", isActive ? "text-brand-strong" : "text-dim")}>
            <Icon className="size-5" />{label}
          </NavLink>
        ))}
        <Sheet open={more} onOpenChange={setMore}>
          <SheetTrigger className={cn("flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px]", NAV.slice(5).some((n) => loc.pathname.startsWith(n.to)) ? "text-brand-strong" : "text-dim")}>
            <Menu className="size-5" />More
          </SheetTrigger>
          <SheetContent side="bottom" className="pb-6">
            <SheetHeader><SheetTitle>More pages</SheetTitle></SheetHeader>
            <ul className="grid gap-1 px-4">
              {NAV.slice(5).map(({ to, label, icon: Icon }) => (
                <li key={to}>
                  <NavLink to={to} onClick={() => setMore(false)} className={({ isActive }) => cn("flex min-h-11 items-center gap-3 rounded-md px-3 text-[15px]", isActive ? "bg-brand-soft text-brand-strong" : "hover:bg-raised")}>
                    <Icon className="size-5" />{label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </SheetContent>
        </Sheet>
      </nav>
    </div>
  );
}

export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-[1600px] space-y-4 p-3 sm:p-5", className)}>{children}</div>;
}

export function Box({ title, right, children, className, pad = true }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={cn("overflow-hidden rounded-xl border border-line bg-panel", className)}>
      {title != null && (
        <header className="flex min-h-11 items-center gap-2 border-b border-line px-4 py-2">
          <h2 className="text-sm font-semibold">{title}</h2>
          <div className="ml-auto flex items-center gap-2">{right}</div>
        </header>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}
