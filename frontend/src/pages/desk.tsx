import { useCallback, useMemo, useState } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Box, Page } from "@/components/shell";
import { Floor, said } from "@/components/floor";
import { AgentSheet, Avatar } from "@/components/panels";
import { Prose } from "@/components/prose";
import { ABOUT, CAST } from "@/lib/cast";
import { useDeskCtx } from "@/lib/desk-context";
import type { DeskEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

const ORDER = ["prices", "headlines", "book", "technical", "news", "bull", "bear", "pm", "risk", "exchange"];
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export default function Desk() {
  const d = useDeskCtx();
  const [agent, setAgent] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const pick = useCallback((id: string) => setAgent(id), []);
  const run = d.runs.find((r) => r.id === d.runId);
  const live = run?.status === "running";
  const last = useMemo(() => {
    const m: Record<string, DeskEvent> = {};
    for (const e of d.events) if (CAST[e.actor]) m[e.actor] = e;
    return m;
  }, [d.events]);
  const log = d.events.filter((e) => CAST[e.actor] && e.kind !== "start");

  return (
    <Page>
      <Box
        title={live ? "Trading floor, live" : "Trading floor"}
        right={
          <>
            <span className="hidden text-xs text-dim sm:inline">{run ? (live ? `Started ${clock(run.started_at)}` : `Last run ${clock(run.started_at)}${run.summary ? `: ${run.summary.split("\n")[0]}` : ""}`) : "No runs yet"}</span>
            <Button size="sm" onClick={d.runNow} disabled={live} className="gap-1.5"><Play className="size-3.5" />{live ? "Running" : "Run the desk now"}</Button>
          </>
        }
      >
        <Floor runId={d.runId} finished={!live} events={d.events} fresh={d.fresh} onPick={pick} />
        <p className="mt-2 text-xs text-dim">Click anyone to see their job and everything they wrote this run. The schedule runs the desk at 01:00, 04:00 and 07:00.</p>
      </Box>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
          {ORDER.map((a) => {
            const e = last[a];
            const mood = !e ? "idle" : e.kind === "start" ? (live ? "working" : "awake") : e.kind === "reject" || e.kind === "error" ? "alert" : "done";
            return (
              <button key={a} type="button" onClick={() => pick(a)} className="flex flex-col gap-2 rounded-xl border border-line bg-panel p-3 text-left transition-colors hover:border-brand/50 hover:bg-raised/40">
                <div className="flex items-center gap-2.5">
                  <Avatar id={a} size={40} mood={mood} />
                  <div className="min-w-0">
                    <p className="font-semibold">{CAST[a].name}</p>
                    <p className="truncate text-xs text-dim">{CAST[a].role}</p>
                  </div>
                  <span className={cn("ml-auto rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase", {
                    idle: "bg-sunk text-dim", awake: "bg-sunk text-dim", working: "bg-brand-soft text-brand-strong", done: "bg-up/12 text-up", alert: "bg-down/12 text-down",
                  }[mood])}>{{ idle: "asleep", awake: "ready", working: "working", done: "done", alert: "objected" }[mood]}</span>
                </div>
                <p className="line-clamp-2 text-[13px] leading-snug">{e ? said(e) : <span className="text-dim">{ABOUT[a].split(".")[0]}.</span>}</p>
              </button>
            );
          })}
        </section>

        <div className="space-y-4">
          <Box title="Tell the desk" right={<span className="text-xs text-dim">Goes into the book they all read</span>}>
            <form onSubmit={(e) => { e.preventDefault(); if (note.trim()) { d.addNote({ kind: "note", text: note }); setNote(""); } }} className="space-y-2">
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="E.g. 'Be careful before the jobs report on Friday' or 'I like ETH shorts below 2,250'" className="min-h-20 text-sm" />
              <div className="flex gap-2">
                <Button size="sm" type="submit" disabled={!note.trim()}>Send</Button>
                <Button size="sm" type="button" variant="outline" disabled={!note.trim() || live} onClick={async () => { await d.addNote({ kind: "note", text: note }); setNote(""); d.runNow(); }}>Send and run now</Button>
              </div>
            </form>
            {d.notes.length > 0 && (
              <ul className="mt-3 space-y-1.5">
                {d.notes.slice(0, 6).map((n) => (
                  <li key={n.id} className="flex items-start justify-between gap-2 rounded-md bg-sunk px-2.5 py-1.5 text-[13px]">
                    <span>{n.asset && <b className="mr-1">{n.asset}</b>}{n.text}</span>
                    <button type="button" className="text-xs text-dim hover:text-down" onClick={() => d.dropNote(n.id)}>remove</button>
                  </li>
                ))}
              </ul>
            )}
          </Box>

          <Box title="Run log" pad={false} right={<span className="text-xs text-dim">{log.length} entries</span>}>
            <ul className="max-h-[480px] divide-y divide-line/60 overflow-y-auto">
              {[...log].reverse().map((e) => (
                <li key={e.id}>
                  <details className="group">
                    <summary className="flex cursor-pointer list-none items-center gap-2.5 px-4 py-2 hover:bg-raised/50">
                      <Avatar id={e.actor} size={22} mood="awake" />
                      <span className="w-16 shrink-0 text-[13px] font-medium">{CAST[e.actor].name}</span>
                      <span className={cn("min-w-0 flex-1 truncate text-[13px]", (e.kind === "reject" || e.kind === "error") && "text-down")}>{e.title}</span>
                      <span className="font-mono text-[11px] text-dim">{clock(e.ts)}</span>
                    </summary>
                    {e.html && <Prose html={e.html} className="border-t border-line/60 bg-sunk/40 px-4 py-3 text-[13px]" />}
                  </details>
                </li>
              ))}
              {!log.length && <li className="px-4 py-6 text-center text-sm text-dim">Nothing yet. Press "Run the desk now".</li>}
            </ul>
          </Box>
        </div>
      </div>
      <AgentSheet id={agent} events={d.events} onClose={() => setAgent(null)} />
    </Page>
  );
}
