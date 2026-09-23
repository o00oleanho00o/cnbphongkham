export type PropMeta = {
  editor?: string;
  default?: unknown;
  options?: unknown[];
  section?: string;
  tsType?: string;
};
export type PropsMeta = Record<string, PropMeta>;
export type PropValues = Record<string, unknown>;

/** Bridge that support.js installs on the page window (same API the claude.ai/design host uses). */
export type DcWindow = Window & {
  __dcRootName?: () => string;
  __dcAnnotatedTemplate?: (name: string) => string | null;
  __dcSetProps?: (name: string, overrides: PropValues | null) => void;
  __dcUpdate?: (name: string, kind: 'html' | 'js' | 'props', content: string, streaming?: boolean) => void;
};

export type Screen = {
  label: string;
  id: string;
  name: string;
  group: string;
  groupTitle: string;
};

type ScreenTemplate = { tpl: string; pattern: string; fromAttr: Map<string, string>; fromText: Map<string, string> };

const SCREEN_ID = /^[A-Z]+\d+$/;
const TOKEN = /\{\{\s*([\s\S]+?)\s*\}\}/g;
const WHOLE_TOKEN = /^\s*\{\{\s*([\s\S]+?)\s*\}\}\s*$/;

// The runtime renders every element with the `data-dc-tpl` id of its template node but drops
// `data-screen-label` from the output, so labels are read from the annotated template instead.
const templateCache = new WeakMap<Window, { source: string; screens: ScreenTemplate[] }>();

function screenTemplates(win: DcWindow): ScreenTemplate[] {
  const root = win.__dcRootName?.();
  const source = (root && win.__dcAnnotatedTemplate?.(root)) || '';
  const cached = templateCache.get(win);
  if (cached?.source === source) return cached.screens;

  const tpl = document.createElement('template');
  tpl.innerHTML = source;
  // Template nodes whose whole text is one `{{ expr }}`: lets a label token be read from rendered text.
  const textTpl = new Map<string, string>();
  for (const el of tpl.content.querySelectorAll('[data-dc-tpl]')) {
    if (el.children.length) continue;
    const m = WHOLE_TOKEN.exec(el.textContent ?? '');
    if (m && !textTpl.has(m[1])) textTpl.set(m[1], el.getAttribute('data-dc-tpl') ?? '');
  }
  const screens = Array.from(tpl.content.querySelectorAll('[data-screen-label][data-dc-tpl]'), (el) => {
    const pattern = el.getAttribute('data-screen-label') ?? '';
    const fromAttr = new Map<string, string>();
    for (const a of el.attributes) {
      const m = WHOLE_TOKEN.exec(a.value);
      if (m && a.name !== 'data-screen-label') fromAttr.set(m[1], a.name);
    }
    return { tpl: el.getAttribute('data-dc-tpl') ?? '', pattern, fromAttr, fromText: textTpl };
  });
  templateCache.set(win, { source, screens });
  return screens;
}

function resolveLabel(t: ScreenTemplate, el: Element) {
  return t.pattern
    .replace(TOKEN, (_, expr: string) => {
      const attr = t.fromAttr.get(expr);
      if (attr) return el.getAttribute(attr) ?? '';
      const textTpl = t.fromText.get(expr);
      if (!textTpl) return '';
      // Nearest enclosing loop item that also rendered the text node carrying this expression.
      for (let up = el.parentElement; up; up = up.parentElement) {
        const hit = up.querySelector(`[data-dc-tpl="${textTpl}"]`);
        if (hit) return hit.textContent?.trim() ?? '';
      }
      return '';
    })
    .trim();
}

/** Rendered screen frames in document order, with their resolved labels. */
export function findScreens(win: DcWindow): { label: string; el: Element }[] {
  const doc = win.document;
  return screenTemplates(win).flatMap((t) =>
    Array.from(doc.querySelectorAll(`[data-dc-tpl="${t.tpl}"]`), (el) => ({ label: resolveLabel(t, el), el })),
  );
}

export function collectScreens(win: DcWindow): Screen[] {
  const doc = win.document;
  return findScreens(win).map(({ label }) => {
    const [head = '', ...rest] = label.split(' · ');
    const hasId = rest.length > 0 && SCREEN_ID.test(head);
    const group = hasId ? head.replace(/\d+$/, '') : '';
    const section = group ? doc.getElementById(group) : null;
    return {
      label,
      id: hasId ? head : '',
      name: hasId ? rest.join(' · ') : label,
      group,
      groupTitle: section?.querySelector('h2')?.textContent?.trim() ?? '',
    };
  });
}

export const sameScreens = (a: Screen[], b: Screen[]) =>
  a.length === b.length && a.every((s, i) => s.label === b[i].label && s.groupTitle === b[i].groupTitle);

/** Splits a .dc.html source into the three parts `__dcUpdate` accepts. */
export function parseDcSource(src: string) {
  const open = /<x-dc(?:\s[^>]*)?>/.exec(src);
  const close = src.lastIndexOf('</x-dc>');
  if (!open || close < open.index) return null;
  const doc = new DOMParser().parseFromString(src, 'text/html');
  const script = doc.querySelector('script[data-dc-script]');
  return {
    template: src.slice(open.index + open[0].length, close),
    js: script?.textContent ?? '',
    props: script?.getAttribute('data-props') ?? '',
  };
}

/** Pushes the latest file into the running page without a reload; false means the caller should reload. */
export async function hotSwap(win: DcWindow, url: string): Promise<boolean> {
  const root = win.__dcRootName?.();
  if (!root || !win.__dcUpdate) return false;
  const res = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
  if (!res.ok) return false;
  const parsed = parseDcSource(await res.text());
  if (!parsed) return false;
  win.__dcUpdate(root, 'props', parsed.props);
  win.__dcUpdate(root, 'html', parsed.template);
  win.__dcUpdate(root, 'js', parsed.js);
  return true;
}
