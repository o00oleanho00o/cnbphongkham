import { memo, type Dispatch, type SetStateAction } from 'react';
import { displayName } from './docs';
import { Icon, IconButton } from './Icon';
import type { Tool } from './useCanvasInput';

export type Panels = { left: boolean; right: boolean };

type ToolbarProps = {
  files: string[];
  file: string;
  onFile: (file: string) => void;
  tool: Tool;
  onTool: (tool: Tool) => void;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onActualSize: () => void;
  onFit: () => void;
  onReload: () => void;
  rawHref: string;
  panels: Panels;
  onPanels: Dispatch<SetStateAction<Panels>>;
  hasProps: boolean;
};

export const Toolbar = memo(function Toolbar(p: ToolbarProps) {
  return (
    <header className="toolbar">
      <div className="brand">
        <span className="brand-mark">pema</span>
        <span className="brand-sub">Design viewer</span>
      </div>

      <nav className="tabs" aria-label="Tài liệu design">
        {p.files.map((f) => (
          <button key={f} type="button" className="tab" aria-pressed={f === p.file} onClick={() => p.onFile(f)}>
            {displayName(f)}
          </button>
        ))}
      </nav>

      <div className="toolbar-group" role="group" aria-label="Công cụ">
        <IconButton
          icon="arrow_selector_tool"
          label="Tương tác — bấm được vào prototype (V)"
          pressed={p.tool === 'interact'}
          onClick={() => p.onTool('interact')}
        />
        <IconButton
          icon="pan_tool"
          label="Kéo khung nhìn (H, hoặc giữ Space)"
          pressed={p.tool === 'hand'}
          onClick={() => p.onTool('hand')}
        />
      </div>

      <div className="toolbar-group" role="group" aria-label="Thu phóng">
        <IconButton icon="remove" label="Thu nhỏ (Ctrl −)" onClick={p.onZoomOut} />
        <button type="button" className="zoom-value" title="Về 100% (Shift+0)" onClick={p.onActualSize}>
          {Math.round(p.zoom * 100)}%
        </button>
        <IconButton icon="add" label="Phóng to (Ctrl +)" onClick={p.onZoomIn} />
        <IconButton icon="fit_screen" label="Vừa khung (Shift+1)" onClick={p.onFit} />
      </div>

      <div className="toolbar-group toolbar-end">
        <IconButton icon="refresh" label="Tải lại trang" onClick={p.onReload} />
        <a className="icon-btn" href={p.rawHref} target="_blank" rel="noreferrer" title="Mở trang gốc trong tab mới" aria-label="Mở trang gốc trong tab mới">
          <Icon name="open_in_new" />
        </a>
        <IconButton
          icon="left_panel_open"
          label="Ẩn / hiện danh sách màn hình"
          pressed={p.panels.left}
          onClick={() => p.onPanels((v) => ({ ...v, left: !v.left }))}
        />
        <IconButton
          icon="right_panel_open"
          label="Ẩn / hiện thuộc tính"
          pressed={p.panels.right && p.hasProps}
          disabled={!p.hasProps}
          onClick={() => p.onPanels((v) => ({ ...v, right: !v.right }))}
        />
      </div>
    </header>
  );
});
