export type Camera = { x: number; y: number; z: number };
export type Rect = { x: number; y: number; w: number; h: number };

export const MIN_ZOOM = 0.05;
export const MAX_ZOOM = 8;

const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

/** Zooms by `factor` while keeping the viewport point (sx, sy) fixed on screen. */
export function zoomAt(c: Camera, sx: number, sy: number, factor: number): Camera {
  const z = clampZoom(c.z * factor);
  const k = z / c.z;
  return { z, x: sx - (sx - c.x) * k, y: sy - (sy - c.y) * k };
}

/** Camera that centres world rect `r` inside a vw × vh viewport. */
export function fitRect(r: Rect, vw: number, vh: number, pad: number, maxZoom = MAX_ZOOM): Camera {
  const availW = Math.max(1, vw - pad * 2);
  const availH = Math.max(1, vh - pad * 2);
  const z = clampZoom(Math.min(availW / r.w, availH / r.h, maxZoom));
  return { z, x: (vw - r.w * z) / 2 - r.x * z, y: (vh - r.h * z) / 2 - r.y * z };
}
