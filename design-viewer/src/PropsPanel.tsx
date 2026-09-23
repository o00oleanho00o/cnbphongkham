import { memo, useMemo } from 'react';
import type { PropMeta, PropsMeta, PropValues } from './dc';
import { Icon } from './Icon';

type PropsPanelProps = {
  meta: PropsMeta | null;
  values: PropValues;
  onChange: (key: string, value: unknown) => void;
  onReset: () => void;
};

const DEFAULT_SECTION = 'Thuộc tính';

const humanize = (key: string) =>
  key
    .replace(/([a-z0-9])([A-Z])/g, (_, a: string, b: string) => `${a} ${b.toLowerCase()}`)
    .replace(/^./, (c) => c.toUpperCase());

const isNumeric = (meta: PropMeta) => meta.editor === 'number' || meta.tsType === 'number';

function inputType(meta: PropMeta) {
  if (meta.editor === 'color') return 'color';
  if (isNumeric(meta)) return 'number';
  return 'text';
}

type FieldProps = {
  name: string;
  meta: PropMeta;
  value: unknown;
  changed: boolean;
  onChange: (key: string, value: unknown) => void;
};

function Field({ name, meta, value, changed, onChange }: FieldProps) {
  const label = (
    <span className="field-label">
      {humanize(name)}
      {changed && <span className="changed-dot" title="Khác giá trị mặc định" />}
    </span>
  );

  if (meta.editor === 'boolean') {
    return (
      <label className="field field-switch">
        {label}
        <input type="checkbox" role="switch" checked={Boolean(value)} onChange={(e) => onChange(name, e.target.checked)} />
      </label>
    );
  }

  if (meta.editor === 'enum' && Array.isArray(meta.options)) {
    return (
      <label className="field">
        {label}
        <select value={String(value ?? '')} onChange={(e) => onChange(name, e.target.value)}>
          {meta.options.map((o) => (
            <option key={String(o)} value={String(o)}>
              {String(o)}
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <label className="field">
      {label}
      <input
        type={inputType(meta)}
        value={String(value ?? '')}
        onChange={(e) => onChange(name, isNumeric(meta) ? Number(e.target.value) : e.target.value)}
      />
    </label>
  );
}

export const PropsPanel = memo(function PropsPanel({ meta, values, onChange, onReset }: PropsPanelProps) {
  const sections = useMemo(() => {
    const bySection = new Map<string, [string, PropMeta][]>();
    for (const entry of Object.entries(meta ?? {})) {
      const title = entry[1].section ?? DEFAULT_SECTION;
      const list = bySection.get(title) ?? [];
      list.push(entry);
      bySection.set(title, list);
    }
    return [...bySection];
  }, [meta]);

  const dirty = Object.keys(values).length > 0;

  return (
    <aside className="panel panel-right" aria-label="Thuộc tính trang">
      <div className="panel-head">
        <h2>Thuộc tính</h2>
        <button type="button" className="text-btn" onClick={onReset} disabled={!dirty}>
          <Icon name="restart_alt" />
          Mặc định
        </button>
      </div>
      <div className="panel-body">
        {sections.map(([title, fields]) => (
          <section key={title} className="group">
            <h3>{title}</h3>
            {fields.map(([key, m]) => (
              <Field
                key={key}
                name={key}
                meta={m}
                value={key in values ? values[key] : m.default}
                changed={key in values}
                onChange={onChange}
              />
            ))}
          </section>
        ))}
        <p className="hint">Đổi giá trị để xem biến thể của trang. File .dc.html không bị sửa.</p>
      </div>
    </aside>
  );
});
