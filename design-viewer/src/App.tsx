import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { fitRect, zoomAt, type Camera } from './camera';
import { findScreens, hotSwap, type PropValues } from './dc';
import { BOTH_HASH, WEB_NEW, WEB_OLD, bothFromHash, displayName, docUrl, fileFromHash, files, type WebSource } from './docs';
import { ExportMenu, type ExportScope } from './ExportMenu';
import {
  DEFAULT_EXPORT,
  EXPORTING_ATTR,
  exportScreens,
  titleOf,
  type ExportProgress,
  type ExportSettings,
} from './exportImage';
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
// "Cả hai": the old web and the Next.js-only canvas side by side in one world, GAP px apart.
const BOTH_GAP = 240;
const BOTH_KEY = 'both';
/** Props that mean the same in both web canvases; `group` differs per file, so it is never copied to the second one. */
const SHARED_PROPS = ['viewport', 'theme', 'showNotes'];
const sharedProps = (values: PropValues): PropValues =>
  Object.fromEntries(Object.entries(values).filter(([k]) => SHARED_PROPS.includes(k)));
const PANELS_KEY = 'dcv:panels';
const EXPORT_KEY = 'dcv:export';
const SELECTION_STYLE_ID = 'dcv-selection';

const isExportShortcut = (e: KeyboardEvent) => (e.ctrlKey || e.metaKey) && e.shiftKey && e.code === 'KeyE';

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
  const [both, setBoth] = useState(bothFromHash);
  const [frameKey, setFrameKey] = useState(0);
  const [tool, setTool] = useState<Tool>('interact');
  const [camera, setCamera] = useState<Camera | null>(() =>
    load<Camera | null>(camKey(bothFromHash() ? BOTH_KEY : fileFromHash()), null),
  );
  const [overrides, setOverrides] = useState<PropValues>(() =>
    load<PropValues>(propsKey(bothFromHash() ? BOTH_KEY : fileFromHash()), {}),
  );
  const [activeScreen, setActiveScreen] = useState('');
  const [panels, setPanels] = useState<Panels>(() => {
    const wide = window.innerWidth >= WIDE_LAYOUT_PX;
    return load<Panels>(PANELS_KEY, { left: wide, right: wide });
  });
  const [exportOpen, setExportOpen] = useState(false);
  const [exportSettings, setExportSettings] = useState<ExportSettings>(() => load(EXPORT_KEY, DEFAULT_EXPORT));
  const [exportProgress, setExportProgress] = useState<ExportProgress | null>(null);
  const [exportMessage, setExportMessage] = useState('');
  const exportingRef = useRef(false);

  const viewportRef = useRef<HTMLElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const frame2Ref = useRef<HTMLIFrameElement>(null);
  const frameId = `${file}#${frameKey}`;
  const file2 = both ? WEB_NEW : '';
  const frame2Id = `${file2}#${frameKey}`;
  const viewKey = both ? BOTH_KEY : file;
  const first = useDcFrame(frameRef, frameId);
  const second = useDcFrame(frame2Ref, frame2Id, both);
  const { root, meta, win } = first;
  const win2 = both ? second.win : null;
  const root2 = second.root;
  const size1 = first.size;
  const secondX = size1.w + BOTH_GAP;
  const size = useMemo(
    () => (both ? { w: secondX + second.size.w, h: Math.max(size1.h, second.size.h) } : size1),
    [both, secondX, second.size, size1],
  );
  const status = both
    ? first.status === 'error' || second.status === 'error'
      ? 'error'
      : first.status === 'ready' && second.status === 'ready'
        ? 'ready'
        : 'loading'
    : first.status;
  const screens = useMemo(() => (both ? [...first.screens, ...second.screens] : first.screens), [both, first.screens, second.screens]);
  const firstRelayout = first.relayout;
  const secondRelayout = second.relayout;
  const relayout = useCallback(() => {
    firstRelayout();
    secondRelayout();
  }, [firstRelayout, secondRelayout]);

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

  const input = useCanvasInput({
    viewportRef,
    win,
    onCamera: updateCamera,
    tool,
    shortcuts: view,
    extra: { win: win2, originX: secondX },
  });

  const selectFile = useCallback((next: string, withBoth = false) => {
    const key = withBoth ? BOTH_KEY : next;
    setFile(next);
    setBoth(withBoth);
    setCamera(load<Camera | null>(camKey(key), null));
    setOverrides(load<PropValues>(propsKey(key), {}));
    setActiveScreen('');
    window.history.replaceState(null, '', `#${withBoth ? BOTH_HASH : encodeURIComponent(next)}`);
  }, []);

  const webSource: WebSource = both ? 'both' : file === WEB_NEW ? 'new' : 'old';
  const selectWebSource = useCallback(
    (source: WebSource) => {
      if (source === 'new') selectFile(WEB_NEW);
      else selectFile(WEB_OLD, source === 'both');
    },
    [selectFile],
  );

  useEffect(() => {
    const onHash = () => selectFile(fileFromHash(), bothFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, [selectFile]);

  useEffect(() => {
    const name = both ? `${displayName(WEB_OLD)} + ${displayName(WEB_NEW)}` : file ? displayName(file) : '';
    document.title = name ? `${name} · Pema design viewer` : 'Pema design viewer';
  }, [file, both]);

  // First visit to a document: wait for the page to settle, then frame all of it.
  useEffect(() => {
    if (status !== 'ready' || camera) return;
    const t = window.setTimeout(view.fit, FIRST_FIT_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [status, camera, view]);

  useEffect(() => {
    if (!camera) return;
    const t = window.setTimeout(() => save(camKey(viewKey), camera), SAVE_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [camera, viewKey]);

  useEffect(() => {
    save(PANELS_KEY, panels);
  }, [panels]);

  // A freshly booted page starts from its own defaults; re-apply the viewer's saved overrides.
  useEffect(() => {
    if (status !== 'ready' || !win || !root) return;
    const saved = overridesRef.current;
    if (Object.keys(saved).length) win.__dcSetProps?.(root, saved);
  }, [status, win, root]);

  // The second page (Cả hai) follows the viewport / theme / notes of the first one.
  useEffect(() => {
    if (!win2 || !root2) return;
    const saved = sharedProps(overridesRef.current);
    if (Object.keys(saved).length) win2.__dcSetProps?.(root2, saved);
  }, [win2, root2]);

  const applyProps = useCallback(
    (next: PropValues) => {
      overridesRef.current = next;
      setOverrides(next);
      save(propsKey(viewKey), next);
      if (win && root) win.__dcSetProps?.(root, Object.keys(next).length ? next : null);
      if (win2 && root2) {
        const shared = sharedProps(next);
        win2.__dcSetProps?.(root2, Object.keys(shared).length ? shared : null);
      }
      relayout();
    },
    [viewKey, win, root, win2, root2, relayout],
  );
  const changeProp = useCallback(
    (key: string, value: unknown) => applyProps({ ...overridesRef.current, [key]: value }),
    [applyProps],
  );
  const resetProps = useCallback(() => applyProps({}), [applyProps]);

  /** The frame element, page and world x-offset that own a screen label (the second page sits at `secondX`). */
  const locate = useCallback(
    (label: string) => {
      const a = win ? findScreens(win).find((s) => s.label === label)?.el : undefined;
      if (a && win) return { el: a, win, ox: 0 };
      const b = win2 ? findScreens(win2).find((s) => s.label === label)?.el : undefined;
      return b && win2 ? { el: b, win: win2, ox: secondX } : null;
    },
    [win, win2, secondX],
  );

  const focusScreen = useCallback(
    (label: string) => {
      const hit = locate(label);
      if (!hit) return;
      const r = hit.el.getBoundingClientRect();
      const v = viewportOf(viewportRef);
      setCamera(fitRect({ x: r.left + hit.ox, y: r.top, w: r.width, h: r.height }, v.w, v.h, SCREEN_PAD, SCREEN_MAX_ZOOM));
      setActiveScreen(label);
      // On narrow screens the list floats over the canvas; get it out of the way of the frame.
      if (window.matchMedia(NARROW_QUERY).matches) setPanels((p) => ({ ...p, left: false }));
    },
    [locate],
  );

  // ---------- Figma-like export ----------
  const selected = useMemo(() => screens.find((s) => s.label === activeScreen), [screens, activeScreen]);
  const selectedSize = useMemo(() => {
    const el = selected ? locate(selected.label)?.el : undefined;
    const frame = (el?.parentElement ?? el) as HTMLElement | undefined;
    return frame ? { w: Math.round(frame.offsetWidth), h: Math.round(frame.offsetHeight) } : null;
  }, [selected, locate, exportOpen]);
  const groupLabels = useMemo(
    () => (selected?.group ? screens.filter((s) => s.group === selected.group).map((s) => s.label) : []),
    [screens, selected],
  );

  const changeExportSettings = useCallback((next: ExportSettings) => {
    setExportSettings(next);
    save(EXPORT_KEY, next);
  }, []);

  const runExport = useCallback(
    async (labels: string[], zipName: string) => {
      if ((!win && !win2) || exportingRef.current || !labels.length) return;
      exportingRef.current = true;
      setExportMessage('');
      try {
        // each page exports the labels it owns; with both pages open a mixed selection gives one download per page
        const owners = [win, win2].filter((w): w is NonNullable<typeof win> => !!w);
        let n = 0;
        for (const w of owners) {
          const mine = new Set(findScreens(w).map((s) => s.label));
          const part = labels.filter((l) => mine.has(l));
          const name = owners.length > 1 && w === win2 ? `${zipName} · Màn mới` : zipName;
          if (part.length) n += await exportScreens(w, part, exportSettings, name, setExportProgress);
        }
        setExportMessage(n ? `Đã xuất ${n} ảnh ${exportSettings.format.toUpperCase()} @${exportSettings.scale}x.` : 'Không tìm thấy màn để xuất.');
      } catch (e) {
        setExportMessage(`Xuất ảnh lỗi: ${e instanceof Error ? e.message : String(e)}`);
        setExportOpen(true);
      } finally {
        exportingRef.current = false;
        setExportProgress(null);
      }
    },
    [win, win2, exportSettings],
  );

  const exportScope = useCallback(
    (scope: ExportScope) => {
      const base = both ? `${displayName(WEB_OLD)} + ${displayName(WEB_NEW)}` : displayName(file);
      if (scope === 'screen' && selected) runExport([selected.label], selected.label);
      if (scope === 'group' && selected?.group) runExport(groupLabels, `${base} · ${selected.group}`);
      if (scope === 'all') runExport(screens.map((s) => s.label), base);
    },
    [file, both, selected, groupLabels, screens, runExport],
  );

  const exportOne = useCallback(
    (label: string) => {
      setActiveScreen(label);
      runExport([label], label);
    },
    [runExport],
  );

  // Click a frame's title on the canvas to select it (double click also zooms to it), like Figma.
  useEffect(() => {
    const detach = [win, win2].flatMap((w) => {
      if (!w) return [];
      const doc = w.document;
      const hit = (target: EventTarget | null) => {
        const node = target as Node | null;
        if (!node) return undefined;
        return findScreens(w).find((s) => titleOf(s.el)?.contains(node))?.label;
      };
      const onClick = (e: MouseEvent) => {
        const label = hit(e.target);
        if (label) setActiveScreen(label);
      };
      const onDblClick = (e: MouseEvent) => {
        const label = hit(e.target);
        if (label) focusScreen(label);
      };
      doc.addEventListener('click', onClick);
      doc.addEventListener('dblclick', onDblClick);
      return [
        () => {
          doc.removeEventListener('click', onClick);
          doc.removeEventListener('dblclick', onDblClick);
        },
      ];
    });
    return () => detach.forEach((d) => d());
  }, [win, win2, focusScreen]);

  // Selection outline on the page, keyed by the frame id so it survives re-renders and hot swaps.
  useEffect(() => {
    for (const w of [win, win2]) {
      const doc = w?.document;
      if (!doc?.head) continue;
      let style = doc.getElementById(SELECTION_STYLE_ID) as HTMLStyleElement | null;
      if (!style) {
        style = doc.createElement('style');
        style.id = SELECTION_STYLE_ID;
        doc.head.appendChild(style);
      }
      const id = selected?.id;
      style.textContent = id
        ? `html:not([${EXPORTING_ATTR}]) [id="${id}"]{outline:2px solid #0B4F94;outline-offset:6px}`
        : '';
    }
  }, [win, win2, selected]);

  // Ctrl/⌘ + Shift + E: export the selected frame (or open the export panel when nothing is selected).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!isExportShortcut(e)) return;
      e.preventDefault();
      if (selected) runExport([selected.label], selected.label);
      else setExportOpen(true);
    };
    window.addEventListener('keydown', onKey);
    win?.addEventListener('keydown', onKey);
    win2?.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      win?.removeEventListener('keydown', onKey);
      win2?.removeEventListener('keydown', onKey);
    };
  }, [win, win2, selected, runExport]);

  // Dev server only: swap the edited document into the running page so camera and prototype state survive.
  useEffect(() => {
    const hot = import.meta.hot;
    if (!hot) return;
    const onChanged = ({ file: changed }: { file: string }) => {
      if (changed === 'support.js') {
        reload();
        return;
      }
      const target = changed === file ? win : changed === file2 ? win2 : null;
      if (!target) return;
      hotSwap(target, docUrl(changed))
        .then((ok) => (ok ? relayout() : reload()))
        .catch(reload);
    };
    hot.on('dc:changed', onChanged);
    return () => hot.off('dc:changed', onChanged);
  }, [file, file2, win, win2, relayout, reload]);

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
  const frameStyle = useMemo(() => ({ width: size1.w, height: size1.h }), [size1.w, size1.h]);
  const frame2Style = useMemo(() => ({ width: second.size.w, height: second.size.h }), [second.size.w, second.size.h]);
  const worldFlex = useMemo(
    () => ({ ...worldStyle, display: 'flex', alignItems: 'flex-start', gap: BOTH_GAP }) as const,
    [worldStyle],
  );

  return (
    <div className="app">
      <Toolbar
        files={files}
        file={file}
        onFile={(next) => selectFile(next)}
        webSource={webSource}
        onWebSource={selectWebSource}
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
        exportSlot={
          <ExportMenu
            open={exportOpen}
            onOpenChange={setExportOpen}
            settings={exportSettings}
            onSettings={changeExportSettings}
            selected={selected}
            selectedSize={selectedSize}
            groupCount={groupLabels.length}
            total={screens.length}
            progress={exportProgress}
            message={exportMessage}
            onExport={exportScope}
          />
        }
      />

      {panels.left && <ScreensPanel screens={screens} active={activeScreen} onSelect={focusScreen} onExport={exportOne} />}

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
          <div className="world" data-canvas-bg="" style={both ? worldFlex : worldStyle}>
            <iframe
              key={`first:${frameId}`}
              ref={frameRef}
              className="page"
              src={docUrl(file)}
              title={displayName(file)}
              scrolling="no"
              style={frameStyle}
            />
            {both && (
              <iframe
                key={`second:${frame2Id}`}
                ref={frame2Ref}
                className="page"
                src={docUrl(file2)}
                title={displayName(file2)}
                scrolling="no"
                style={frame2Style}
              />
            )}
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
