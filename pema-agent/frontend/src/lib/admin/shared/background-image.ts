// ported from: web/src/shared/background-image.ts
//
// Deviation: Pema keeps the light-blue wave artwork for identity areas only (login, page hero), never
// behind tables or clinical text (design skill: visual-system). So the dashboard shell does not use this;
// only the login page does. The original had two raster backgrounds for light/dark; Pema has one SVG,
// whose soft strokes read on both token sets.
import type { Theme } from "./use-theme";

export function anhNen(_theme: Theme): string {
  return "/care-waves.svg";
}
