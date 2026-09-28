import { domToBlob } from 'modern-screenshot';
import { findScreens, type DcWindow } from './dc';
import { zipFiles, type ZipEntry } from './zip';

export type ExportFormat = 'png' | 'jpg';
export type ExportSettings = { scale: 1 | 2 | 3; format: ExportFormat };
export const DEFAULT_EXPORT: ExportSettings = { scale: 2, format: 'png' };
export const EXPORT_SCALES: ExportSettings['scale'][] = [1, 2, 3];

/**
 * Set on the page's <html> while exporting: the viewer's selection outline
 * (`html:not([data-dcv-exporting]) #A1 { outline … }`) must never show in images.
 */
export const EXPORTING_ATTR = 'data-dcv-exporting';

const UNSAFE = /[\\/:*?"<>|\u0000-\u001f]+/g;

/** Figma-style file name: "A1 · Hôm nay@2x.png" (safe on Windows/macOS). */
export function exportName(label: string, s: ExportSettings) {
  const base = label.replace(UNSAFE, '-').replace(/\s+/g, ' ').trim() || 'screen';
  return `${base}${s.scale === 1 ? '' : `@${s.scale}x`}.${s.format}`;
}

export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/**
 * Rasterises one screen frame from the page (the phone frame = the screen's parent, same area as
 * the `canvas-shots.cjs` reference images), with fonts and icon fonts embedded.
 */
async function renderFrame(screen: Element, s: ExportSettings): Promise<Blob> {
  const frame = screen.parentElement ?? screen;
  const html = screen.ownerDocument.documentElement;
  const cssText = await pageFontCss(screen.ownerDocument);
  html.setAttribute(EXPORTING_ATTR, '');
  try {
    await screen.ownerDocument.fonts?.ready;
    return await domToBlob(frame, {
      scale: s.scale,
      type: s.format === 'jpg' ? 'image/jpeg' : 'image/png',
      quality: 0.92,
      // JPG has no transparency: fill the rounded corners like the canvas background.
      backgroundColor: s.format === 'jpg' ? '#ffffff' : null,
      font: cssText ? { cssText } : undefined,
      timeout: 30_000,
    });
  } finally {
    html.removeAttribute(EXPORTING_ATTR);
  }
}

/** The id badge + name row above a screen frame on the canvas (screen → phone frame → column). */
export function titleOf(screen: Element): Element | null {
  return screen.parentElement?.parentElement?.firstElementChild ?? null;
}

export type ExportProgress = { done: number; total: number };

const FONT_CSS = /^https:\/\/fonts\.googleapis\.com\//;
const fontCss = new Map<string, Promise<string>>();

async function dataUrl(url: string) {
  const blob = await (await fetch(url, { mode: 'cors' })).blob();
  return await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

/** One Google Fonts stylesheet with every `url(...)` inlined as a data URL (cached per session). */
function inlinedFontCss(href: string): Promise<string> {
  let cached = fontCss.get(href);
  if (!cached) {
    cached = (async () => {
      const css = await (await fetch(href, { mode: 'cors' })).text();
      const urls = [...new Set([...css.matchAll(/url\((['"]?)([^'")]+)\1\)/g)].map((m) => m[2]))];
      const inlined = await Promise.all(urls.map(async (u) => [u, await dataUrl(u)] as const));
      return inlined.reduce((acc, [u, data]) => acc.split(u).join(data), css);
    })();
    cached.catch(() => fontCss.delete(href));
    fontCss.set(href, cached);
  }
  return cached;
}

/**
 * Web fonts of the page (Be Vietnam Pro, Material Symbols icon font). The browser hides
 * cross-origin stylesheet rules from scripts, so they are fetched (Google Fonts allows CORS) and
 * embedded explicitly – otherwise icons export as their ligature names ("calendar_month").
 */
async function pageFontCss(doc: Document): Promise<string> {
  const links = [...doc.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')]
    .map((l) => l.href)
    .filter((href) => FONT_CSS.test(href));
  return (await Promise.all(links.map(inlinedFontCss))).join('\n');
}


/**
 * Exports the screens with the given labels: one image downloads directly, several are packed
 * into `<zipName>.zip`. Returns the number of images written.
 */
export async function exportScreens(
  win: DcWindow,
  labels: string[],
  s: ExportSettings,
  zipName: string,
  onProgress?: (p: ExportProgress) => void,
): Promise<number> {
  const byLabel = new Map(findScreens(win).map((x) => [x.label, x.el]));  const targets = labels.flatMap((label) => {
    const el = byLabel.get(label);
    return el ? [{ label, el }] : [];
  });
  if (!targets.length) return 0;

  if (targets.length === 1) {
    onProgress?.({ done: 0, total: 1 });
    download(await renderFrame(targets[0].el, s), exportName(targets[0].label, s));
    onProgress?.({ done: 1, total: 1 });
    return 1;
  }

  const entries: ZipEntry[] = [];
  for (const [i, t] of targets.entries()) {
    onProgress?.({ done: i, total: targets.length });
    entries.push({ name: exportName(t.label, s), data: await renderFrame(t.el, s) });
  }
  onProgress?.({ done: targets.length, total: targets.length });
  download(await zipFiles(entries), `${zipName.replace(UNSAFE, '-')}.zip`);
  return entries.length;
}
