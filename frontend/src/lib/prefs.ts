import { useState } from "react";

/** A setting kept in this browser only. Falls back to the default when storage is blocked. */
export function usePref<T>(key: string, fallback: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? fallback : { ...(fallback as object), ...JSON.parse(raw) } as T;
    } catch {
      return fallback;
    }
  });
  const set = (v: T) => {
    setValue(v);
    try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* storage blocked */ }
  };
  return [value, set];
}
