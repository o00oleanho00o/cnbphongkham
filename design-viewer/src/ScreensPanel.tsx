import { memo, useMemo, useState } from 'react';
import type { Screen } from './dc';
import { Icon } from './Icon';

type ScreensPanelProps = {
  screens: Screen[];
  active: string;
  onSelect: (label: string) => void;
};

type Group = { key: string; title: string; items: Screen[] };

export const ScreensPanel = memo(function ScreensPanel({ screens, active, onSelect }: ScreensPanelProps) {
  const [query, setQuery] = useState('');

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const byKey = new Map<string, Group>();
    for (const s of screens) {
      if (q && !s.label.toLowerCase().includes(q)) continue;
      let g = byKey.get(s.group);
      if (!g) {
        g = { key: s.group, title: s.groupTitle || 'Màn hình', items: [] };
        byKey.set(s.group, g);
      }
      g.items.push(s);
    }
    return [...byKey.values()];
  }, [screens, query]);

  return (
    <aside className="panel panel-left" aria-label="Danh sách màn hình">
      <div className="panel-head">
        <h2>Màn hình</h2>
        <span className="count">{screens.length}</span>
      </div>
      <label className="search">
        <Icon name="search" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tìm theo mã hoặc tên"
          aria-label="Tìm màn hình"
        />
      </label>

      <div className="panel-body">
        {groups.length === 0 && (
          <p className="empty">{screens.length ? 'Không có màn hình khớp.' : 'Đang đọc danh sách màn hình…'}</p>
        )}
        {groups.map((g) => (
          <section key={g.key || 'all'} className="group">
            <h3>
              {g.key && <span className="group-code">{g.key}</span>}
              <span>{g.title}</span>
            </h3>
            <ul>
              {g.items.map((s) => (
                <li key={s.label}>
                  <button
                    type="button"
                    className="screen-item"
                    aria-current={s.label === active || undefined}
                    onClick={() => onSelect(s.label)}
                  >
                    {s.id && <span className="screen-id">{s.id}</span>}
                    <span className="screen-name">{s.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <dl className="shortcuts">
        <dt>Cuộn</dt>
        <dd>Kéo khung nhìn</dd>
        <dt>Ctrl + cuộn</dt>
        <dd>Phóng to / nhỏ</dd>
        <dt>Giữ Space</dt>
        <dd>Kéo bằng chuột</dd>
        <dt>Shift + 1 / 0</dt>
        <dd>Vừa khung / 100%</dd>
      </dl>
    </aside>
  );
});
