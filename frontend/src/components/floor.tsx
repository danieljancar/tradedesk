import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CAST, figure, gradients, Rig } from "@/lib/cast";
import type { DeskEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

const W = 1200, H = 470;
const POS: Record<string, [number, number]> = {
  prices: [100, 115], headlines: [100, 240], book: [100, 365],
  technical: [345, 140], news: [345, 345],
  bull: [605, 140], bear: [605, 345],
  pm: [855, 242],
  risk: [1095, 140], exchange: [1095, 345],
};
const LANES = [
  { x: 100, label: "Data" }, { x: 345, label: "Analysts" }, { x: 605, label: "Debate" },
  { x: 855, label: "Decision" }, { x: 1095, label: "Rules & orders" },
];
const EDGES: [string, string][] = [
  ["prices", "technical"], ["book", "technical"], ["headlines", "news"],
  ["technical", "bull"], ["technical", "bear"], ["news", "bull"], ["news", "bear"],
  ["bull", "pm"], ["bear", "pm"], ["pm", "risk"], ["risk", "exchange"],
];
export const STEPS = [
  { id: "data", label: "Data", actors: ["prices", "headlines", "book"] },
  { id: "analysts", label: "Analysts", actors: ["technical", "news"] },
  { id: "debate", label: "Debate", actors: ["bull", "bear"] },
  { id: "decision", label: "Decision", actors: ["pm"] },
  { id: "risk", label: "Risk check", actors: ["risk", "exchange"] },
];
export const START_LINES: Record<string, string> = {
  prices: "Pulling candles and funding…", headlines: "Reading the news feeds…", book: "Opening the books…",
  technical: "Studying the charts…", news: "Checking headlines and the calendar…",
  bull: "Looking for a reason to buy…", bear: "Looking for what could go wrong…",
  pm: "Weighing both sides…", risk: "Measuring every idea against the rules…", exchange: "Preparing orders…",
};
export const said = (e: DeskEvent) => (e.kind === "start" && START_LINES[e.actor]) || e.title;

function edgePath(a: string, b: string) {
  const [x1, y1] = POS[a], [x2, y2] = POS[b];
  const sx = x1 + 54, ex = x2 - 56, mid = (sx + ex) / 2;
  return `M${sx} ${y1} C${mid} ${y1}, ${mid} ${y2}, ${ex} ${y2}`;
}

const STATIC_SVG = `
  <defs>${gradients()}
    <linearGradient id="edge-flow" x1="0" x2="1"><stop offset="0" stop-color="var(--flow)" stop-opacity="0"/><stop offset=".5" stop-color="var(--flow)"/><stop offset="1" stop-color="var(--flow)" stop-opacity="0"/></linearGradient>
  </defs>
  <g aria-hidden="true">${LANES.map((l) => `
    <rect class="lane" x="${l.x - 94}" y="16" width="188" height="${H - 32}" rx="28"/>
    <text class="lane-label" x="${l.x}" y="44">${l.label.toUpperCase()}</text>`).join("")}
  </g>
  <g aria-hidden="true">${EDGES.map(([a, b]) => `<path class="edge" data-from="${a}" data-to="${b}" d="${edgePath(a, b)}"/>`).join("")}</g>
  <g class="packets" aria-hidden="true"></g>
  <g>${Object.entries(CAST).map(([id, c]) => `
    <g class="char is-idle" data-id="${id}" data-kind="${c.kind}" data-mood="idle" transform="translate(${POS[id][0]} ${POS[id][1]})"
       tabindex="0" role="button" aria-label="${c.name}, ${c.role}. Open">
      <g class="lean">${figure(id)}</g>
      <text class="name" y="${c.kind === "device" ? 66 : 77}">${c.name}</text>
      <text class="status" y="${c.kind === "device" ? 83 : 94}">asleep</text>
    </g>`).join("")}
  </g>`;

type Bubble = { id: number; actor: string; text: string };

export function Floor({ runId, finished, events, fresh, onPick, hideSteps = false }: {
  runId: string | null; finished: boolean; events: DeskEvent[]; fresh: DeskEvent[]; onPick: (id: string) => void; hideSteps?: boolean;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const rig = useRef<Rig | null>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [steps, setSteps] = useState<Record<string, string>>({});
  const calm = useRef(matchMedia("(prefers-reduced-motion: reduce)"));

  useLayoutEffect(() => {
    const el = svg.current!;
    el.innerHTML = STATIC_SVG;
    rig.current = new Rig(el, { calm: calm.current });
    const pick = (e: Event) => {
      const g = (e.target as Element).closest<SVGGElement>(".char[data-id]");
      if (!g) return;
      if (e instanceof KeyboardEvent && e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      onPick(g.dataset.id!);
    };
    el.addEventListener("click", pick);
    el.addEventListener("keydown", pick);
    return () => {
      rig.current?.destroy();
      el.removeEventListener("click", pick);
      el.removeEventListener("keydown", pick);
    };
  }, [onPick]);

  const setMood = (actor: string, mood: string) => {
    rig.current?.mood(actor, mood);
    svg.current?.querySelectorAll(`.edge[data-to="${actor}"]`).forEach((e) => e.classList.toggle("flow", mood === "working"));
    svg.current?.querySelectorAll(`.edge[data-from="${actor}"]`).forEach((e) => e.classList.toggle("lit", mood === "done"));
  };

  const packet = (from: string, to: string) => {
    if (calm.current.matches) return;
    const path = svg.current?.querySelector<SVGPathElement>(`.edge[data-from="${from}"][data-to="${to}"]`);
    const layer = svg.current?.querySelector(".packets");
    if (!path || !layer) return;
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("r", "5");
    dot.setAttribute("class", "packet");
    layer.append(dot);
    const total = path.getTotalLength(), t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 1100);
      const e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      const p = path.getPointAtLength(total * e);
      dot.setAttribute("cx", String(p.x));
      dot.setAttribute("cy", String(p.y));
      if (k < 1) requestAnimationFrame(step); else dot.remove();
    };
    requestAnimationFrame(step);
  };

  const apply = (ev: DeskEvent, live: boolean) => {
    const a = ev.actor;
    if (a === "desk" && ev.kind === "start") Object.keys(CAST).forEach((id) => setMood(id, "idle"));
    if (!CAST[a]) return;
    if (ev.kind === "start") {
      setMood(a, "working");
      if (live) ev.refs?.forEach((r) => packet(r, a));
    } else if (ev.kind === "reject" || ev.kind === "error") {
      if (rig.current?.get(a)?.dataset.mood !== "done") setMood(a, "alert");
    } else setMood(a, "done");
    if (live) {
      const text = said(ev);
      const short = text.length > 96 ? `${text.slice(0, 94)}…` : text;
      const id = ev.id;
      setBubbles((b) => [...b.filter((x) => x.actor !== a), { id, actor: a, text: short }]);
      rig.current?.talk(a, Math.min(2600, short.length * 11 + 300));
      setTimeout(() => setBubbles((b) => b.filter((x) => x.id !== id)), 9000);
    }
  };

  const refreshSteps = () => {
    const out: Record<string, string> = {};
    for (const s of STEPS) {
      const moods = s.actors.map((x) => rig.current?.get(x)?.dataset.mood);
      out[s.id] = moods.includes("working") ? "now"
        : moods.every((m) => m === "done" || m === "alert" || (finished && m === "awake")) && moods.some((m) => m !== "awake") ? "done"
          : moods.some((m) => m === "done") ? "now" : "";
    }
    setSteps(out);
  };

  // replay the whole run when it changes, without animation
  useEffect(() => {
    Object.keys(CAST).forEach((id) => setMood(id, "idle"));
    setBubbles([]);
    events.forEach((e) => apply(e, false));
    if (finished) {
      // a finished run has nobody still working: whoever never reported back just goes back to rest
      for (const id of Object.keys(CAST)) if (rig.current?.get(id)?.dataset.mood === "working") setMood(id, "awake");
    }
    refreshSteps();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, events.length === 0, finished]);

  useEffect(() => {
    fresh.forEach((e) => apply(e, true));
    refreshSteps();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fresh]);

  return (
    <div className="space-y-4">
      {!hideSteps && <ol className="flex flex-wrap gap-1.5" aria-label="Progress of this run">
        {STEPS.map((s, i) => (
          <li key={s.id} className={cn("step", steps[s.id])}>
            <span className="step-pip" aria-hidden="true">{steps[s.id] === "done" ? "✓" : i + 1}</span>{s.label}
          </li>
        ))}
      </ol>}
      <div className="stage-scroll">
        <div className="stage">
          <svg ref={svg} viewBox={`0 0 ${W} ${H}`} className="floor" role="group" aria-label="The desk: data feeds, analysts, debate, decision, risk check and exchange" />
          <div className="pointer-events-none absolute inset-0" aria-hidden="true">
            <AnimatePresence>
              {bubbles.map((b) => (
                <motion.div
                  key={b.id}
                  className="bubble"
                  style={{ left: `${(POS[b.actor][0] / W) * 100}%`, top: `${(POS[b.actor][1] / H) * 100}%` }}
                  initial={{ opacity: 0, y: 8, scale: 0.9 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -6, scale: 0.96 }}
                  transition={{ type: "spring", stiffness: 420, damping: 28 }}
                >
                  <Typed text={b.text} />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}

function Typed({ text }: { text: string }) {
  const [n, setN] = useState(() => (matchMedia("(prefers-reduced-motion: reduce)").matches ? text.length : 0));
  useEffect(() => {
    if (n >= text.length) return;
    const t = setTimeout(() => setN((x) => Math.min(text.length, x + 2)), 22);
    return () => clearTimeout(t);
  }, [n, text]);
  return <>{text.slice(0, n)}</>;
}
