import type { ComponentType } from "react";

/** The screen a route file registers, for a test that renders it without a router. */
export function componentOf(route: { options: { component?: unknown } }): ComponentType {
  const { component } = route.options;
  if (typeof component !== "function") throw new Error("the route registers no component");
  // `component` is the function the route file passed to `createFileRoute`: a component, not a lazy loader.
  return component as ComponentType;
}
