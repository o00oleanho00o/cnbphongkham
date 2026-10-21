import { useRouter } from "@tanstack/react-router";
import type { ComponentProps, MouseEvent } from "react";

type LinkProps = Omit<ComponentProps<"a">, "href"> & { href: string; replace?: boolean };

const EXTERNAL = /^([a-z][a-z0-9+.-]*:|\/\/)/i;

/**
 * An anchor that moves through the router (no page reload) on a plain left click. Takes a path with its query
 * (`/guide?a=x`) like the `next/link` it replaced, so the screens do not need the typed `to`/`search` of TanStack's
 * own Link. Outside a router (a unit test) the click is the browser's.
 */
export function Link({ href, replace, onClick, target, ...rest }: LinkProps) {
  const router = useRouter({ warn: false });

  function handleClick(e: MouseEvent<HTMLAnchorElement>): void {
    onClick?.(e);
    const plain = e.button === 0 && !(e.metaKey || e.ctrlKey || e.shiftKey || e.altKey);
    if (e.defaultPrevented || !router || !plain || EXTERNAL.test(href)) return;
    if (target !== undefined && target !== "_self") return;
    e.preventDefault();
    router.history[replace ? "replace" : "push"](href);
  }

  return <a href={href} target={target} onClick={handleClick} {...rest} />;
}
