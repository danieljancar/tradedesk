import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Shell } from "@/components/shell";
import { TermLayer } from "@/components/term";
import { DeskProvider } from "@/lib/desk-context";
import Overview from "@/pages/overview";
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

export default function App() {
  const { dark, toggle } = useTheme();
  return (
    <BrowserRouter>
      <TooltipProvider>
        <DeskProvider>
          <TermLayer>
            <Shell dark={dark} toggle={toggle}>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/markets" element={<Markets />} />
                <Route path="/markets/:asset" element={<Markets />} />
                <Route path="/desk" element={<Desk />} />
                <Route path="/trades" element={<Trades />} />
                <Route path="/news" element={<News />} />
                <Route path="/learn" element={<Learn />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Shell>
            <Toaster position="top-center" theme={dark ? "dark" : "light"} />
          </TermLayer>
        </DeskProvider>
      </TooltipProvider>
    </BrowserRouter>
  );
}
