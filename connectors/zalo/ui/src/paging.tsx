/** Infinite scroll for the lists of the plugin, on TanStack Query: five lines first, five more at each end of the list. */
import { QueryClient, QueryClientProvider, useInfiniteQuery } from "@tanstack/react-query";
import { type ReactNode, type RefObject, useEffect, useRef } from "react";

import { PAGE_SIZE } from "./logic";

// One client for every list of the plugin. The pages are cut from a list the screen already holds, so they never go
// stale and never need a retry or a refetch on focus.
const client = new QueryClient({
  defaultOptions: { queries: { staleTime: Infinity, retry: false, refetchOnWindowFocus: false } },
});

export function PagingProvider({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/**
 * The first lines of `items` and a marker to put under the last one: when the marker comes into view (inside `rootRef`'s
 * box, or the window when there is none) the next five lines are fetched. The marker is watched again after every
 * page, so a box that five lines do not fill keeps loading until it overflows. `key` tells the list from the others in
 * the query cache; a new key (or a new length) starts over from the first five.
 */
export function usePaged<T>(key: readonly unknown[], items: readonly T[], rootRef?: RefObject<Element | null>) {
  const endRef = useRef<HTMLDivElement>(null);
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ["zalo-pages", ...key, items.length],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => items.slice(pageParam, pageParam + PAGE_SIZE),
    getNextPageParam: (last, pages) => (last.length === PAGE_SIZE ? pages.length * PAGE_SIZE : undefined),
  });
  const shown = data?.pages.flat() ?? [];

  useEffect(() => {
    const end = endRef.current;
    if (end === null || !hasNextPage || isFetchingNextPage) return;
    const watcher = new IntersectionObserver(
      (seen) => {
        if (seen.some((entry) => entry.isIntersecting)) void fetchNextPage();
      },
      { root: rootRef?.current ?? null },
    );
    watcher.observe(end);
    return () => watcher.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, shown.length, rootRef]);

  return { shown, loaded: data !== undefined, hasNext: hasNextPage, endRef };
}
