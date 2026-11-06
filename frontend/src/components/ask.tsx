import { useEffect, useRef, useState } from "react";
import { MessageCircle, SendHorizontal } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { Prose } from "@/components/prose";
import { api, useInterval } from "@/lib/api";
import { cn } from "@/lib/utils";

type Item = { id: string; question: string; answer: string; status: "thinking" | "done" | "error"; asked_at: string };

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
const html = (t: string) => esc(t).split(/\n{2,}/).map((p) => `<p>${p.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>")}</p>`).join("");

export function Ask() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Item[]>([]);
  const [q, setQ] = useState("");
  const list = useRef<HTMLDivElement>(null);
  const thinking = items.some((i) => i.status === "thinking");
  const load = () => api<Item[]>("/api/ask").then(setItems).catch(() => {});

  useEffect(() => { if (open) load(); }, [open]);
  useInterval(() => { if (open && thinking) load(); }, 2000);
  // scroll only the chat, scrollIntoView would also move the page behind the sheet
  useEffect(() => {
    const el = list.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items.length, thinking, open]);

  const send = async () => {
    const question = q.trim();
    if (!question || thinking) return;
    setQ("");
    try {
      const res = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json", "X-Desk": "1" }, body: JSON.stringify({ question }) });
      if (!res.ok) throw new Error((await res.json()).detail);
      load();
    } catch (e: any) { toast.error(e.message); setQ(question); }
  };

  return (
    <>
      <Button variant="ghost" size="sm" className="h-8 gap-1.5" onClick={() => setOpen(true)} aria-label="Ask the desk">
        <MessageCircle className="size-4" /><span className="hidden sm:inline">Ask</span>
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="flex w-full flex-col gap-0 p-0 sm:max-w-lg">
          <SheetHeader className="border-b border-line px-4 py-3"><SheetTitle>Ask the desk</SheetTitle></SheetHeader>
          <div ref={list} className="flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4">
            {!items.length && <p className="text-sm text-dim">Questions about the market, the news or the desk's trades. Answers can take up to a minute.</p>}
            {items.map((i) => (
              <div key={i.id} className="space-y-2">
                <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-brand-soft px-3 py-2 text-[14px] text-brand-strong">{i.question}</p>
                {i.status === "thinking"
                  ? <p className="w-fit animate-pulse rounded-lg bg-sunk px-3 py-2 text-[14px] text-dim">Thinking…</p>
                  : <div className={cn("max-w-[95%] rounded-lg bg-sunk px-3 py-2", i.status === "error" && "text-down")}><Prose html={html(i.answer)} className="text-[14px]" /></div>}
              </div>
            ))}
          </div>
          <form className="flex items-end gap-2 border-t border-line p-3" onSubmit={(e) => { e.preventDefault(); send(); }}>
            <Textarea value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="e.g. what happened with the Nasdaq today?" className="max-h-40 min-h-11 flex-1 text-[15px]" aria-label="Question" />
            <Button type="submit" size="icon" className="size-11" disabled={!q.trim() || thinking} aria-label="Send"><SendHorizontal className="size-4" /></Button>
          </form>
        </SheetContent>
      </Sheet>
    </>
  );
}
