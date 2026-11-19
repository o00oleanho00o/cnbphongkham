import { createRouter, parseSearchWith, stringifySearchWith } from "@tanstack/react-router";

import { routeTree } from "./routeTree.gen";

export function getRouter() {
  return createRouter({
    routeTree,
    scrollRestoration: true,
    defaultPreload: false,
    // Query values stay the strings the user typed: the default codec turns "7" into 7 and "1e3" into 1000, and the
    // screens read every value with `URLSearchParams.get`.
    parseSearch: parseSearchWith((value) => value),
    stringifySearch: stringifySearchWith(JSON.stringify),
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof getRouter>;
  }
}
