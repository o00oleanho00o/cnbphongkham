import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from 'react';
import { zoomAt, type Camera } from './camera';
import type { DcWindow } from './dc';

export type Tool = 'interact' | 'hand';
export type CameraUpdate = (update: (c: Camera) => Camera) => void;
export type Shortcuts = {
  zoomIn: () => void;
  zoomOut: () => void;
  actualSize: () => void;
  fit: () => void;
  setTool: (tool: Tool) => void;
};

type Options = {
  viewportRef: RefObject<HTMLElement | null>;
  win: DcWindow | null;
  onCamera: CameraUpdate;
  tool: Tool;
  shortcuts: Shortcuts;
};

type Point = { x: number; y: number };

const LINE_PX = 16;
const PAGE_PX = 800;
// A mouse wheel notch with Ctrl is ~100px; pinch gestures send small deltas. Clamping keeps both smooth.
const MAX_ZOOM_DELTA = 50;
const ZOOM_SPEED = 0.01;
const SCROLLABLE = /(auto|scroll|overlay)/;
const EDITABLE_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

function wheelDelta(e: WheelEvent) {
  const unit = e.deltaMode === 1 ? LINE_PX : e.deltaMode === 2 ? PAGE_PX : 1;
  const dx = e.deltaX * unit;
  const dy = e.deltaY * unit;
  if (e.shiftKey && dx === 0) return { dx: dy, dy: 0 };
  return { dx, dy };
}

function applyWheel(e: WheelEvent, onCamera: CameraUpdate, anchor: (c: Camera) => Point) {
  const { dx, dy } = wheelDelta(e);
  if (e.ctrlKey || e.metaKey) {
    const d = Math.max(-MAX_ZOOM_DELTA, Math.min(MAX_ZOOM_DELTA, e.deltaY * (e.deltaMode === 1 ? LINE_PX : 1)));
    onCamera((c) => {
      const p = anchor(c);
      return zoomAt(c, p.x, p.y, Math.exp(-d * ZOOM_SPEED));
    });
    return;
  }
  onCamera((c) => ({ ...c, x: c.x - dx, y: c.y - dy }));
}

// Targets may come from the page's iframe realm, so this duck-types instead of using instanceof.
function isEditable(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el || typeof el.tagName !== 'string') return false;
  return el.isContentEditable || EDITABLE_TAGS.has(el.tagName);
}

/** True when an element under the pointer can still scroll in the wheel's direction. */
function canScroll(target: EventTarget | null, dx: number, dy: number) {
  let el = target as Element | null;
  if (!el || typeof el.getBoundingClientRect !== 'function') return false;
  const doc = el.ownerDocument;
  const view = doc.defaultView;
  if (!view) return false;
  for (; el && el !== doc.body && el !== doc.documentElement; el = el.parentElement) {
    const cs = view.getComputedStyle(el);
    const scrollsY = SCROLLABLE.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 1;
    const scrollsX = SCROLLABLE.test(cs.overflowX) && el.scrollWidth > el.clientWidth + 1;
    const roomY = dy > 0 ? el.scrollTop + el.clientHeight < el.scrollHeight - 1 : dy < 0 && el.scrollTop > 0;
    const roomX = dx > 0 ? el.scrollLeft + el.clientWidth < el.scrollWidth - 1 : dx < 0 && el.scrollLeft > 0;
    if ((scrollsY && roomY) || (scrollsX && roomX)) return true;
  }
  return false;
}

/**
 * Canvas navigation shared by the viewer and the embedded page: wheel pans, Ctrl/⌘ + wheel
 * (or pinch) zooms at the pointer, Space or the hand tool drags. Inside the page, wheel over a
 * scrollable area scrolls it, so prototypes stay usable.
 */
export function useCanvasInput({ viewportRef, win, onCamera, tool, shortcuts }: Options) {
  const [spaceHeld, setSpaceHeld] = useState(false);
  const [dragging, setDragging] = useState(false);
  const panActive = tool === 'hand' || spaceHeld;

  const live = useRef({ onCamera, shortcuts, panActive });
  useLayoutEffect(() => {
    live.current = { onCamera, shortcuts, panActive };
  });
  const last = useRef<Point | null>(null);

  const onKeyDown = useCallback((e: KeyboardEvent) => {
    if (isEditable(e.target)) return;
    const s = live.current.shortcuts;
    const mod = e.ctrlKey || e.metaKey;
    if (e.code === 'Space') {
      e.preventDefault();
      if (!e.repeat) setSpaceHeld(true);
      return;
    }
    if (mod && (e.key === '=' || e.key === '+')) {
      e.preventDefault();
      s.zoomIn();
      return;
    }
    if (mod && e.key === '-') {
      e.preventDefault();
      s.zoomOut();
      return;
    }
    if (mod && e.key === '0') {
      e.preventDefault();
      s.actualSize();
      return;
    }
    if (mod || e.altKey) return;
    if (e.shiftKey && e.code === 'Digit1') {
      e.preventDefault();
      s.fit();
      return;
    }
    if (e.shiftKey && e.code === 'Digit0') {
      e.preventDefault();
      s.actualSize();
      return;
    }
    if (e.shiftKey) return;
    if (e.key === 'h' || e.key === 'H') s.setTool('hand');
    if (e.key === 'v' || e.key === 'V') s.setTool('interact');
  }, []);

  const onKeyUp = useCallback((e: KeyboardEvent) => {
    if (e.code === 'Space') setSpaceHeld(false);
  }, []);

  useEffect(() => {
    const release = () => setSpaceHeld(false);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('blur', release);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', release);
    };
  }, [onKeyDown, onKeyUp]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = viewport.getBoundingClientRect();
      const p = { x: e.clientX - r.left, y: e.clientY - r.top };
      applyWheel(e, live.current.onCamera, () => p);
    };
    viewport.addEventListener('wheel', onWheel, { passive: false });
    return () => viewport.removeEventListener('wheel', onWheel);
  }, [viewportRef]);

  useEffect(() => {
    if (!win) return;
    const onWheel = (e: WheelEvent) => {
      const zooming = e.ctrlKey || e.metaKey;
      if (!zooming && !live.current.panActive) {
        const { dx, dy } = wheelDelta(e);
        if (canScroll(e.target, dx, dy)) return;
      }
      e.preventDefault();
      // Page coordinates are world coordinates: the iframe sits at the world origin, unscrolled.
      applyWheel(e, live.current.onCamera, (c) => ({ x: c.x + e.clientX * c.z, y: c.y + e.clientY * c.z }));
    };
    win.addEventListener('wheel', onWheel, { passive: false });
    win.addEventListener('keydown', onKeyDown);
    win.addEventListener('keyup', onKeyUp);
    return () => {
      win.removeEventListener('wheel', onWheel);
      win.removeEventListener('keydown', onKeyDown);
      win.removeEventListener('keyup', onKeyUp);
    };
  }, [win, onKeyDown, onKeyUp]);

  const handlers = useMemo(() => {
    const end = () => {
      if (!last.current) return;
      last.current = null;
      setDragging(false);
    };
    return {
      onPointerDown: (e: ReactPointerEvent<HTMLElement>) => {
        if (e.button !== 0 && e.button !== 1) return;
        const target = e.target as HTMLElement;
        const onBackground = target === e.currentTarget || 'canvasBg' in target.dataset;
        if (!onBackground && e.button !== 1 && !live.current.panActive) return;
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        last.current = { x: e.clientX, y: e.clientY };
        setDragging(true);
      },
      onPointerMove: (e: ReactPointerEvent<HTMLElement>) => {
        const from = last.current;
        if (!from) return;
        const dx = e.clientX - from.x;
        const dy = e.clientY - from.y;
        last.current = { x: e.clientX, y: e.clientY };
        live.current.onCamera((c) => ({ ...c, x: c.x + dx, y: c.y + dy }));
      },
      onPointerUp: end,
      onPointerCancel: end,
    };
  }, []);

  return { panActive, dragging, handlers };
}
