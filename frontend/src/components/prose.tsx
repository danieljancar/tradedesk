import DOMPurify from "dompurify";
import { useLayoutEffect, useRef } from "react";
import { annotate } from "@/lib/learn";
import { cn } from "@/lib/utils";

/** Server-rendered Markdown (raw HTML disabled server-side), with glossary words made tappable. */
export function Prose({ html, className, strip }: { html: string; className?: string; strip?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.innerHTML = DOMPurify.sanitize(html);
    if (strip) el.querySelectorAll(strip).forEach((n) => n.remove());
    annotate(el);
  }, [html, strip]);
  return <div ref={ref} className={cn("prose-desk", className)} />;
}
