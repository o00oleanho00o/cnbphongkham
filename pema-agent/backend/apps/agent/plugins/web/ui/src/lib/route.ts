/** Hash routing (`#/plugins`): the gateway serves one index.html, so the page lives after the `#`. */
import { useSyncExternalStore } from "react";

function current(): string {
  const path = window.location.hash.replace(/^#/, "");
  return path.startsWith("/") ? path : "/";
}

function subscribe(listener: () => void): () => void {
  window.addEventListener("hashchange", listener);
  return () => window.removeEventListener("hashchange", listener);
}

export function useRoute(): string {
  return useSyncExternalStore(subscribe, current);
}

export function navigate(path: string): void {
  window.location.hash = path;
}
