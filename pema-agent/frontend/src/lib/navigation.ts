import {
  useLocation,
  useParams as useRouteParams,
  useRouter as useTanStackRouter,
} from "@tanstack/react-router";
import { useMemo } from "react";

// The `next/navigation` hooks the screens were written against, on top of TanStack Router. Paths are plain
// strings with their query, as before.
// shortcut: a query key given twice keeps its last value (the screens read one value per key); move a screen to
// typed `navigate({ to, search })` when it is next edited.

type NavigateOptions = {
  /** `false` keeps the scroll position, for a change of `?tab=` on the page that is already open. */
  scroll?: boolean;
};

export function useRouter() {
  const router = useTanStackRouter();
  return useMemo(() => {
    const go = (href: string, replace: boolean, options?: NavigateOptions) => {
      const url = new URL(href, "http://localhost");
      void router.navigate({
        to: url.pathname,
        search: Object.fromEntries(url.searchParams),
        hash: url.hash.slice(1),
        replace,
        resetScroll: options?.scroll !== false,
      });
    };
    return {
      push: (href: string, options?: NavigateOptions) => go(href, false, options),
      replace: (href: string, options?: NavigateOptions) => go(href, true, options),
      back: () => router.history.back(),
      refresh: () => void router.invalidate(),
    };
  }, [router]);
}

export const usePathname = (): string => useLocation({ select: (l) => l.pathname });

export function useSearchParams(): URLSearchParams {
  const search = useLocation({ select: (l) => l.searchStr });
  return useMemo(() => new URLSearchParams(search), [search]);
}

export function useParams<T extends Record<string, string>>(): T {
  // `strict: false` returns the params of every route on the path; each screen names the ones its route has.
  return useRouteParams({ strict: false }) as unknown as T;
}
