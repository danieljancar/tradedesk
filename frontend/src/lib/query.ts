import { QueryClient, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, gcTime: 15 * 60_000, retry: 1, refetchOnWindowFocus: true },
  },
});

/** GET with a shared cache: pages show the last answer at once and refresh it in the background. */
export function useApi<T>(path: string | null, opts: { every?: number; stale?: number } = {}) {
  return useQuery<T, Error>({
    queryKey: [path],
    queryFn: () => api<T>(path!),
    enabled: !!path,
    staleTime: opts.stale,
    refetchInterval: opts.every,
  });
}

export const refetch = (path: string) => queryClient.invalidateQueries({ queryKey: [path] });
