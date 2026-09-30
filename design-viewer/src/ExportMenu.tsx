import { memo, useEffect, useRef } from 'react';
import type { Screen } from './dc';
import { EXPORT_SCALES, type ExportFormat, type ExportProgress, type ExportSettings } from './exportImage';
import { Icon } from './Icon';

export type ExportScope = 'screen' | 'group' | 'all';

type ExportMenuProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  settings: ExportSettings;
  onSettings: (s: ExportSettings) => void;
  selected: Screen | undefined;
  /** CSS size of the selected frame (what one image covers before scaling). */
  selectedSize: { w: number; h: number } | null;
  groupCount: number;
  total: number;
  progress: ExportProgress | null;
  message: string;
  onExport: (scope: ExportScope) => void;
};

const FORMATS: ExportFormat[] = ['png', 'jpg'];

/** Figma-like export panel: scale + format, then the selected frame, its group or everything. */
export const ExportMenu = memo(function ExportMenu(p: ExportMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  const busy = !!p.progress && p.progress.done < p.progress.total;

  useEffect(() => {
    if (!p.open) return;
    const onDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) p.onOpenChange(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && p.onOpenChange(false);
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [p.open, p.onOpenChange]);

  return (
    <div className="export" ref={ref}>
      <button
        type="button"
        className="icon-btn"
        title="Xuất ảnh màn hình (Ctrl+Shift+E)"
        aria-label="Xuất ảnh màn hình"
        aria-expanded={p.open}
        aria-pressed={p.open}
        onClick={() => p.onOpenChange(!p.open)}
      >
        <Icon name={busy ? 'hourglass_top' : 'ios_share'} filled={p.open} />
      </button>

      {p.open && (
        <div className="export-pop" role="dialog" aria-label="Xuất ảnh màn hình">
          <h2>Xuất ảnh</h2>

          <div className="export-row">
            <span>Tỉ lệ</span>
            <div className="segmented" role="radiogroup" aria-label="Tỉ lệ">
              {EXPORT_SCALES.map((scale) => (
                <button
                  key={scale}
                  type="button"
                  role="radio"
                  aria-checked={p.settings.scale === scale}
                  onClick={() => p.onSettings({ ...p.settings, scale })}
                >
                  {scale}x
                </button>
              ))}
            </div>
          </div>
          <div className="export-row">
            <span>Định dạng</span>
            <div className="segmented" role="radiogroup" aria-label="Định dạng">
              {FORMATS.map((format) => (
                <button
                  key={format}
                  type="button"
                  role="radio"
                  aria-checked={p.settings.format === format}
                  onClick={() => p.onSettings({ ...p.settings, format })}
                >
                  {format.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <p className="export-size">
            {p.selectedSize
              ? `${p.selected?.id || p.selected?.name}: ${p.selectedSize.w * p.settings.scale} × ${p.selectedSize.h * p.settings.scale} px`
              : `Màn điện thoại 390 × 844 → ${390 * p.settings.scale} × ${844 * p.settings.scale} px`}
          </p>

          <button
            type="button"
            className="export-btn primary"
            disabled={!p.selected || busy}
            onClick={() => p.onExport('screen')}
          >
            <Icon name="download" />
            {p.selected ? `Xuất ${p.selected.id || p.selected.name}` : 'Chọn một màn để xuất'}
          </button>
          <button
            type="button"
            className="export-btn"
            disabled={!p.selected?.group || busy}
            onClick={() => p.onExport('group')}
          >
            <Icon name="folder_zip" />
            {p.selected?.group ? `Nhóm ${p.selected.group} · ${p.groupCount} màn (.zip)` : 'Nhóm của màn đang chọn (.zip)'}
          </button>
          <button type="button" className="export-btn" disabled={!p.total || busy} onClick={() => p.onExport('all')}>
            <Icon name="folder_zip" />
            Tất cả · {p.total} màn (.zip)
          </button>

          {p.progress && busy && (
            <div className="export-progress" role="status">
              <progress value={p.progress.done} max={p.progress.total} />
              <span>
                Đang xuất {p.progress.done}/{p.progress.total}…
              </span>
            </div>
          )}
          {!busy && p.message && (
            <p className="export-msg" role="status">
              {p.message}
            </p>
          )}
          <p className="export-hint">
            Chọn màn: bấm vào tên màn trên canvas (bấm đúp để phóng tới) hoặc trong danh sách. Nút tải xuống cạnh từng
            màn trong danh sách xuất ngay màn đó.
          </p>
        </div>
      )}
    </div>
  );
});
