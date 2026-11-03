import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { GLOSSARY } from "@/lib/learn";
import { cn } from "@/lib/utils";

type Open = (key: string, el: HTMLElement) => void;
const Ctx = createContext<Open>(() => {});

/** One shared popover for every glossary word on the page, including words inside agent reports. */
export function TermLayer({ children }: { children: ReactNode }) {
  const [key, setKey] = useState<string | null>(null);
  const anchor = useRef<HTMLElement | null>(null);
  const virtualRef = useRef({ getBoundingClientRect: () => anchor.current?.getBoundingClientRect() ?? new DOMRect() });
  const open = useCallback<Open>((k, el) => { anchor.current = el; setKey(k); }, []);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const b = (e.target as HTMLElement).closest<HTMLElement>("button.term[data-term]");
      if (b && !b.dataset.react) { e.preventDefault(); open(b.dataset.term!, b); }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [open]);

  const g = key ? GLOSSARY[key] : null;
  return (
    <Ctx.Provider value={open}>
      {children}
      <Popover open={!!g} onOpenChange={(o) => !o && setKey(null)}>
        <PopoverAnchor virtualRef={virtualRef as any} />
        <PopoverContent className="w-80 text-sm leading-relaxed" sideOffset={8}>
          {g && (
            <div className="space-y-2">
              <p className="font-heading text-base font-semibold">{g.term}</p>
              <p>{g.short}</p>
              {g.long && <p className="text-muted-foreground">{g.long}</p>}
            </div>
          )}
        </PopoverContent>
      </Popover>
    </Ctx.Provider>
  );
}

export function Term({ k, children, className }: { k: string; children?: ReactNode; className?: string }) {
  const open = useContext(Ctx);
  return (
    <button
      type="button"
      data-term={k}
      data-react="1"
      className={cn("term", className)}
      onClick={(e) => open(k, e.currentTarget)}
    >
      {children ?? GLOSSARY[k]?.term}
    </button>
  );
}
