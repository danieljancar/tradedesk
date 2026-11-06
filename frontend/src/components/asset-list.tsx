import { useState, type ReactNode } from "react";
import { NavLink } from "react-router";
import { ChevronDown, GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";

const read = <T,>(key: string, fallback: T): T => {
  try { return JSON.parse(localStorage.getItem(key) ?? "null") ?? fallback; } catch { return fallback; }
};
const write = (key: string, value: unknown) => {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage blocked */ }
};

/** Saved order first, anything new (a fresh scan pick) at the end. */
function ordered(ids: string[], saved: string[]) {
  return [...saved.filter((x) => ids.includes(x)), ...ids.filter((x) => !saved.includes(x))];
}

export type Row = { id: string; label: ReactNode; sub?: ReactNode; value?: ReactNode; change?: ReactNode; title?: string };

export function AssetGroup({ id, title, rows, active }: { id: string; title: string; rows: Row[]; active: string }) {
  const [open, setOpen] = useState(() => read(`markets.open.${id}`, true));
  const [saved, setSaved] = useState<string[]>(() => read(`markets.order.${id}`, []));
  const [drag, setDrag] = useState<string | null>(null);
  const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
  const order = ordered(rows.map((r) => r.id), saved);

  const toggle = () => { setOpen(!open); write(`markets.open.${id}`, !open); };
  const save = (next: string[]) => { setSaved(next); write(`markets.order.${id}`, next); };
  const move = (from: string, to: string) => {
    if (from === to) return;
    const next = order.filter((x) => x !== from);
    next.splice(order.indexOf(to), 0, from);
    save(next);
  };
  // Alt + arrow keys move the focused row
  const nudge = (row: string, by: number) => {
    const i = order.indexOf(row), j = i + by;
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[i], next[j]] = [next[j], next[i]];
    save(next);
  };

  return (
    <div className="shrink-0 xl:shrink">
      <button type="button" onClick={toggle} aria-expanded={open}
        className="flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-[11px] font-semibold tracking-[0.08em] text-dim uppercase hover:text-fg">
        {title}<ChevronDown className={cn("size-3.5 transition-transform", !open && "-rotate-90")} />
      </button>
      {open && (
        <ul className="flex gap-1 xl:block xl:space-y-0.5">
          {order.map((key) => {
            const r = byId[key];
            return (
              <li key={key} draggable onDragStart={() => setDrag(key)} onDragEnd={() => setDrag(null)}
                onDragOver={(e) => { e.preventDefault(); if (drag && drag !== key) move(drag, key); }}
                className={cn("group relative shrink-0", drag === key && "opacity-50")}>
                <NavLink to={`/markets/${key}`} title={r.title}
                  onKeyDown={(e) => { if (e.altKey && e.key === "ArrowUp") { e.preventDefault(); nudge(key, -1); } if (e.altKey && e.key === "ArrowDown") { e.preventDefault(); nudge(key, 1); } }}
                  className={() => cn("flex items-center justify-between gap-3 rounded-md py-2 pr-2.5 pl-5 hover:bg-raised", key === active && "bg-raised")}>
                  <GripVertical aria-hidden className="absolute left-0.5 size-3.5 cursor-grab text-dim opacity-0 group-hover:opacity-100" />
                  <span>
                    <span className="block font-semibold">{r.label}</span>
                    {r.sub && <span className="block text-[10px] font-medium text-dim">{r.sub}</span>}
                  </span>
                  <span className="text-right">
                    <span className="block font-mono text-[13px] tabular-nums">{r.value ?? "–"}</span>
                    {r.change}
                  </span>
                </NavLink>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
