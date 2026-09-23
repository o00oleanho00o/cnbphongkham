import { useCallback, useEffect, useState, type RefObject } from 'react';
import { collectScreens, sameScreens, type DcWindow, type PropsMeta, type Screen } from './dc';

export type Size = { w: number; h: number };
export type FrameStatus = 'loading' | 'ready' | 'error';

/** Layout width the page gets before it is measured; also the floor for its size. */
export const BASE_SIZE: Size = { w: 1280, h: 900 };

const BOOT_TIMEOUT_MS = 20000;
const SCREENS_DEBOUNCE_MS = 250;

// The iframe is sized to its content, so the page must not scroll itself, and the
// runtime's full-page `height:100%` would otherwise pin the body to the iframe height.
const FRAME_CSS =
  'html,body{overflow:hidden!important;height:auto!important}#dc-root,#dc-root>.sc-host{height:auto!important}';

type Booted = { type: '__dc_booted'; rootName: string; propsMeta: PropsMeta | null };

const isBooted = (data: unknown): data is Booted =>
  typeof data === 'object' && data !== null && (data as { type?: unknown }).type === '__dc_booted';

/** Tracks one .dc page inside an iframe: boot, props metadata, screen list and content size. */
export function useDcFrame(frameRef: RefObject<HTMLIFrameElement | null>, frameId: string) {
  const [status, setStatus] = useState<FrameStatus>('loading');
  const [root, setRoot] = useState('');
  const [meta, setMeta] = useState<PropsMeta | null>(null);
  const [screens, setScreens] = useState<Screen[]>([]);
  const [size, setSize] = useState<Size>(BASE_SIZE);
  const [win, setWin] = useState<DcWindow | null>(null);

  useEffect(() => {
    setStatus('loading');
    setRoot('');
    setMeta(null);
    setScreens([]);
    setSize(BASE_SIZE);
    setWin(null);
    // support.js posts this after boot and again whenever the root's props metadata changes.
    const onMessage = (e: MessageEvent) => {
      const frameWin = frameRef.current?.contentWindow;
      if (!frameWin || e.source !== frameWin || !isBooted(e.data)) return;
      setRoot(e.data.rootName);
      setMeta(e.data.propsMeta);
      setWin(frameWin as DcWindow);
      setStatus('ready');
    };
    window.addEventListener('message', onMessage);
    const timer = window.setTimeout(() => setStatus((s) => (s === 'loading' ? 'error' : s)), BOOT_TIMEOUT_MS);
    return () => {
      window.removeEventListener('message', onMessage);
      window.clearTimeout(timer);
    };
  }, [frameRef, frameId]);

  useEffect(() => {
    const doc = win?.document;
    if (!win || !doc?.body) return;
    const style = doc.createElement('style');
    style.textContent = FRAME_CSS;
    doc.head.appendChild(style);

    let disposed = false;
    let raf = 0;
    let screensTimer = 0;
    const measure = () => {
      raf = 0;
      if (disposed) return;
      // body.scrollWidth: with overflow hidden on <html>, the root's scrollWidth is clamped to the frame.
      const w = Math.max(BASE_SIZE.w, doc.body.scrollWidth, doc.documentElement.scrollWidth);
      const h = Math.max(BASE_SIZE.h, doc.body.offsetHeight);
      setSize((prev) => (prev.w === w && prev.h === h ? prev : { w, h }));
    };
    const scheduleMeasure = () => {
      if (!raf && !disposed) raf = win.requestAnimationFrame(measure);
    };
    const refreshScreens = () => {
      if (disposed) return;
      const next = collectScreens(win);
      setScreens((prev) => (sameScreens(prev, next) ? prev : next));
    };
    const onMutate = () => {
      scheduleMeasure();
      win.clearTimeout(screensTimer);
      screensTimer = win.setTimeout(refreshScreens, SCREENS_DEBOUNCE_MS);
    };

    // Observers come from the page's own realm so they attach cleanly to its nodes.
    const realm = win as unknown as typeof globalThis;
    const mutations = new realm.MutationObserver(onMutate);
    mutations.observe(doc.body, { subtree: true, childList: true, attributes: true, characterData: true });
    const resizes = new realm.ResizeObserver(scheduleMeasure);
    resizes.observe(doc.body);
    doc.fonts?.ready.then(scheduleMeasure).catch(() => undefined);
    measure();
    refreshScreens();

    return () => {
      disposed = true;
      mutations.disconnect();
      resizes.disconnect();
      if (raf) win.cancelAnimationFrame(raf);
      win.clearTimeout(screensTimer);
      style.remove();
    };
  }, [win]);

  // Width only ever grows while measuring (content can't shrink below the frame), so an
  // explicit change such as a prop edit resets to the base width and lets it re-grow.
  const relayout = useCallback(() => setSize(BASE_SIZE), []);

  return { status, root, meta, screens, size, win, relayout };
}
