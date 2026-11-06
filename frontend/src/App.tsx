import { type ReactNode, useEffect, useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Crash } from "@/components/crash";
import { Shell } from "@/components/shell";
import { queryClient } from "@/lib/query";
import { TermLayer } from "@/components/term";
import { DeskProvider } from "@/lib/desk-context";
import Overview from "@/pages/overview";
import Portfolio from "@/pages/portfolio";
import Performance from "@/pages/performance";
import Markets from "@/pages/markets";
import Desk from "@/pages/desk";
import Trades from "@/pages/trades";
import News from "@/pages/news";
import Learn from "@/pages/learn";
import Settings from "@/pages/settings";

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

function Pages({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <Crash reset={pathname}><Routes>{children}</Routes></Crash>;
}

export default function App() {
  const { dark, toggle } = useTheme();
  return (
    <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <TooltipProvider>
        <DeskProvider>
          <TermLayer>
            <Shell dark={dark} toggle={toggle}>
              <Pages>
                <Route path="/" element={<Overview />} />
                <Route path="/portfolio" element={<Portfolio />} />
                <Route path="/markets" element={<Markets />} />
                <Route path="/markets/:asset" element={<Markets />} />
                <Route path="/desk" element={<Desk />} />
                <Route path="/trades" element={<Trades />} />
                <Route path="/performance" element={<Performance />} />
                <Route path="/news" element={<News />} />
                <Route path="/learn" element={<Learn />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Pages>
            </Shell>
            <Toaster position="top-center" theme={dark ? "dark" : "light"} />
          </TermLayer>
        </DeskProvider>
      </TooltipProvider>
    </BrowserRouter>
    </QueryClientProvider>
  );
}
