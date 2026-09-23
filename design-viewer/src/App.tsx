import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { fitRect, zoomAt, type Camera } from './camera';
import { findScreens, hotSwap, type PropValues } from './dc';
import { displayName, docUrl, fileFromHash, files } from './docs';
import { PropsPanel } from './PropsPanel';
import { ScreensPanel } from './ScreensPanel';
import { StatusOverlay } from './StatusOverlay';
import { load, save } from './storage';
import { Toolbar, type Panels } from './Toolbar';
import { useCanvasInput, type Shortcuts, type Tool } from './useCanvasInput';
import { useDcFrame } from './useDcFrame';

const DEFAULT_CAMERA: Camera = { x: 48, y: 48, z: 0.5 };
const FIT_PAD = 48;
const SCREEN_PAD = 56;
const SCREEN_MAX_ZOOM = 2;
const ZOOM_STEP = 1.25;
const FIRST_FIT_DELAY_MS = 400;
const SAVE_DELAY_MS = 300;
const DOT_GAP = 24;
const WIDE_LAYOUT_PX = 900;
const NARROW_QUERY = '(max-width: 720px)';

const camKey = (file: string) => `dcv:cam:${file}`;
const propsKey = (file: string) => `dcv:props:${file}`;
const PANELS_KEY = 'dcv:panels';

function viewportOf(ref: RefObject<HTMLElement | null>) {
  const r = ref.current?.getBoundingClientRect();
  return { w: r?.width ?? 0, h: r?.height ?? 0 };
}

/** Keeps the dot grid between half and double its base spacing at any zoom. */
function dotGap(z: number) {
  let gap = DOT_GAP * z;
  if (gap <= 0) return DOT_GAP;
  while (gap < DOT_GAP / 2) gap *= 2;
  while (gap > DOT_GAP * 2) gap /= 2;
  return gap;
}

export function App() {
  const [file, setFile] = useState(fileFromHash);
  const [frameKey, setFrameKey] = useState(0);
  const [tool, setTool] = useState<Tool>('interact');
  const [camera, setCamera] = useState<Camera | null>(() => load<Camera | null>(camKey(fileFromHash()), null));
  const [overrides, setOverrides] = useState<PropValues>(() => load<PropValues>(propsKey(fileFromHash()), {}));
  const [activeScreen, setActiveScreen] = useState('');
  const [panels, setPanels] = useState<Panels>(() => {
    const wide = window.innerWidth >= WIDE_LAYOUT_PX;
    return load<Panels>(PANELS_KEY, { left: wide, right: wide });
  });

  const viewportRef = useRef<HTMLElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const frameId = `${file}#${frameKey}`;
  const { status, root, meta, screens, size, win, relayout } = useDcFrame(frameRef, frameId);

  const sizeRef = useRef(size);
  const overridesRef = useRef(overrides);
  useEffect(() => {
    sizeRef.current = size;
  }, [size]);
  useEffect(() => {
    overridesRef.current = overrides;
  }, [overrides]);

  const updateCamera = useCallback((update: (c: Camera) => Camera) => setCamera((c) => update(c ?? DEFAULT_CAMERA)), []);
  const reload = useCallback(() => setFrameKey((k) => k + 1), []);

  const view = useMemo<Shortcuts>(() => {
    const zoomCentered = (factor: (c: Camera) => number) =>
      updateCamera((c) => {
        const v = viewportOf(viewportRef);
        return zoomAt(c, v.w / 2, v.h / 2, factor(c));
      });
    return {
      zoomIn: () => zoomCentered(() => ZOOM_STEP),
      zoomOut: () => zoomCentered(() => 1 / ZOOM_STEP),
      actualSize: () => zoomCentered((c) => 1 / c.z),
      fit: () => {
        const v = viewportOf(viewportRef);
        const s = sizeRef.current;
        setCamera(fitRect({ x: 0, y: 0, w: s.w, h: s.h }, v.w, v.h, FIT_PAD, 1));
      },
      setTool,
    };
  }, [updateCamera]);

  const input = useCanvasInput({ viewportRef, win, onCamera: updateCamera, tool, shortcuts: view });

  const selectFile = useCallback((next: string) => {
    setFile(next);
    setCamera(load<Camera | null>(camKey(next), null));
    setOverrides(load<PropValues>(propsKey(next), {}));
    setActiveScreen('');
    window.history.replaceState(null, '', `#${encodeURIComponent(next)}`);
  }, []);

  useEffect(() => {
    const onHash = () => selectFile(fileFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, [selectFile]);

  useEffect(() => {
    document.title = file ? `${displayName(file)} · Pema design viewer` : 'Pema design viewer';
  }, [file]);

  // First visit to a document: wait for the page to settle, then frame all of it.
  useEffect(() => {
    if (status !== 'ready' || camera) return;
    const t = window.setTimeout(view.fit, FIRST_FIT_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [status, camera, view]);

  useEffect(() => {
    if (!camera) return;
    const t = window.setTimeout(() => save(camKey(file), camera), SAVE_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [camera, file]);

  useEffect(() => {
    save(PANELS_KEY, panels);
  }, [panels]);

  // A freshly booted page starts from its own defaults; re-apply the viewer's saved overrides.
  useEffect(() => {
    if (status !== 'ready' || !win || !root) return;
    const saved = overridesRef.current;
    if (Object.keys(saved).length) win.__dcSetProps?.(root, saved);
  }, [status, win, root]);

  const applyProps = useCallback(
    (next: PropValues) => {
      overridesRef.current = next;
      setOverrides(next);
      save(propsKey(file), next);
      if (win && root) win.__dcSetProps?.(root, Object.keys(next).length ? next : null);
      relayout();
    },
    [file, win, root, relayout],
  );
  const changeProp = useCallback(
    (key: string, value: unknown) => applyProps({ ...overridesRef.current, [key]: value }),
    [applyProps],
  );
  const resetProps = useCallback(() => applyProps({}), [applyProps]);

  const focusScreen = useCallback(
    (label: string) => {
      const el = win ? findScreens(win).find((s) => s.label === label)?.el : undefined;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const v = viewportOf(viewportRef);
      setCamera(fitRect({ x: r.left, y: r.top, w: r.width, h: r.height }, v.w, v.h, SCREEN_PAD, SCREEN_MAX_ZOOM));
      setActiveScreen(label);
      // On narrow screens the list floats over the canvas; get it out of the way of the frame.
      if (window.matchMedia(NARROW_QUERY).matches) setPanels((p) => ({ ...p, left: false }));
    },
    [win],
  );

  // Dev server only: swap the edited document into the running page so camera and prototype state survive.
  useEffect(() => {
    const hot = import.meta.hot;
    if (!hot) return;
    const onChanged = ({ file: changed }: { file: string }) => {
      if (changed === 'support.js') {
        reload();
        return;
      }
      if (changed !== file || !win) return;
      hotSwap(win, docUrl(file))
        .then((ok) => (ok ? relayout() : reload()))
        .catch(reload);
    };
    hot.on('dc:changed', onChanged);
    return () => hot.off('dc:changed', onChanged);
  }, [file, win, relayout, reload]);

  const cam = camera ?? DEFAULT_CAMERA;
  const gap = dotGap(cam.z);
  const hasProps = !!meta && Object.keys(meta).length > 0;

  const worldStyle = useMemo(
    () => ({ transform: `translate(${cam.x}px, ${cam.y}px) scale(${cam.z})` }),
    [cam.x, cam.y, cam.z],
  );
  const viewportStyle = useMemo(
    () => ({ backgroundSize: `${gap}px ${gap}px`, backgroundPosition: `${cam.x}px ${cam.y}px` }),
    [gap, cam.x, cam.y],
  );
  const frameStyle = useMemo(() => ({ width: size.w, height: size.h }), [size.w, size.h]);

  return (
    <div className="app">
      <Toolbar
        files={files}
        file={file}
        onFile={selectFile}
        tool={tool}
        onTool={setTool}
        zoom={cam.z}
        onZoomIn={view.zoomIn}
        onZoomOut={view.zoomOut}
        onActualSize={view.actualSize}
        onFit={view.fit}
        onReload={reload}
        rawHref={docUrl(file)}
        panels={panels}
        onPanels={setPanels}
        hasProps={hasProps}
      />

      {panels.left && <ScreensPanel screens={screens} active={activeScreen} onSelect={focusScreen} />}

      <main
        ref={viewportRef}
        className="viewport"
        data-tool={tool}
        data-dragging={input.dragging || undefined}
        style={viewportStyle}
        aria-label="Canvas"
        {...input.handlers}
      >
        {file ? (
          <div className="world" data-canvas-bg="" style={worldStyle}>
            <iframe
              key={frameId}
              ref={frameRef}
              className="page"
              src={docUrl(file)}
              title={displayName(file)}
              scrolling="no"
              style={frameStyle}
            />
          </div>
        ) : (
          <p className="no-docs">Không tìm thấy file .dc.html nào trong thư mục canvas.</p>
        )}
        {(input.panActive || input.dragging) && <div className="pan-shield" data-canvas-bg="" />}
        {file && status !== 'ready' && <StatusOverlay status={status} onRetry={reload} />}
      </main>

      {panels.right && hasProps && (
        <PropsPanel meta={meta} values={overrides} onChange={changeProp} onReset={resetProps} />
      )}
    </div>
  );
}
