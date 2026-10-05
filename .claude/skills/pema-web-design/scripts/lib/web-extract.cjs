// In-page extractors for the old Pema web (W2). Text only, no pixels; the old web is never edited.
//
// Both functions are serialised by Playwright (`page.evaluate(fn, arg)`), so each one must be self-contained:
// no closure over Node variables and no require().
//
//   extractInPage({roots, mode, profile})  one structured pass over the open screen: tree + categorised lists + raw style counts
//     profile "next" (W8) reads the Next.js front end (Tailwind classes, role=dialog/note/alert, the kit's Badge and cards)
//     instead of the old web's class names; without it the behaviour is the old-web one, unchanged.
//   probeInPage()                 layout probe of the tagged elements, run again at other viewports
//
// Tree node kinds (key `n`): see web-specs-lib.cjs, the renderer, for how each one becomes a kit component call.
//   group (flex/grid container with `lay`), card, form, nav, text, eyebrow, heading, action, chip, field, badge,
//   kpi, notice, empty, table, facts, fact, list (repeated data rows), progress, avatar, img, icon.

function extractInPage(cfg) {
  const norm = (s) => (s || '').replace(/[ \s]+/g, ' ').trim();
  const NO_WALK = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'LINK', 'META', 'HEAD', 'TITLE', 'OPTION', 'OPTGROUP', 'DATALIST', 'COLGROUP', 'COL', 'SOURCE', 'TRACK', 'PATH', 'CIRCLE', 'RECT', 'LINE', 'POLYLINE', 'POLYGON', 'DEFS', 'G']);
  const INLINE = new Set(['SPAN', 'SMALL', 'STRONG', 'B', 'I', 'EM', 'U', 'SUP', 'SUB', 'BR', 'CODE', 'MARK', 'A', 'S', 'ABBR', 'TIME']);
  const CHIP_BTN = (el) =>
    el.matches('.chip, .tab, .guide-topic, [aria-pressed], [role="tab"], .finance-tabs button, .tabbar button, .ops-toggle button, .crm-groups button');
  const NEXT = cfg.profile === 'next';
  const BADGE_SEL = NEXT
    ? 'span.rounded-pill'
    : '.status, .badge, .rx-status, .nav-badge, .priority, .crm-case, .chip:not(button), .approved, .draft-mark, .urgent, .overdue, .missing';
  const KPI_SEL = NEXT ? '.kpi-none' : '.metric-card, .crm-kpi, .metric, .ops-stat';
  const NOTICE_SEL = NEXT
    ? '[role="alert"], [role="note"], [role="status"]'
    : '.notice, .alert-strip, .ops-error, .crm-error, .photo-disclaimer, .quick-catalog-note, .studio-note, .linked-rx-note, .print-blocked, .draft-mark, .toast, [role="alert"], [role="status"], .guide-context, .guide-handoff, .warning';
  const CARD_SEL = NEXT
    ? '.gc-card, .gc-tile, [role="dialog"]'
    : '.panel, .callout, .ai-card, .followup-card, .resource-card, .service-card, .session-card, .wait-card, .crm-case-card, .mobile-card, .linked-plan, .linked-modal-card, .order-sheet, .hero, .modal, .crm-summary, .patient-hero, .guide-article, .upload-box, .quick-cart, .compare';
  const REPEAT = NEXT ? [] : ['quick-product-row', 'drop-slot', 'booking', 'positioned-booking', 'crm-task-row', 'wait-card', 'timeline-item', 'list-item', 'followup-card', 'resource-card', 'service-card', 'care-row', 'order-history-row', 'crm-case-card', 'item-line', 'event-disclosure', 'room-track', 'time-track', 'week-day'];
  const REPEAT_MIN = 3;
  const NOISE_CLASS = new Set(['active', 'selected', 'clickable', 'ui-icon', 'icon-wrap', 'ico', 'current']);

  const CTRL = 'button, a[href], input:not([type="hidden"]), select, textarea, summary, [role="button"]';
  const hasCtl = (el) => [...el.querySelectorAll(CTRL)].some((c) => vis(c));
  // lucide icon of an element, by the registry of shared/ui.js (cfg.icons: name -> svg inner markup)
  const iconMap = {};
  for (const [name, inner] of Object.entries(cfg.icons || {})) {
    const holder = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    holder.innerHTML = inner;
    iconMap[holder.innerHTML.replace(/\s+/g, '')] = name;
  }
  const iconName = (host) => {
    if (NEXT) return ''; // the kit's icons are not the old web's registry: a name would only say "unknown"
    const svg = host.tagName.toLowerCase() === 'svg' ? host : host.querySelector('svg');
    if (!svg) return '';
    const r = svg.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return '';
    return iconMap[svg.innerHTML.replace(/\s+/g, '')] || 'unknown';
  };
  const withIcon = (n, el) => {
    const ic = iconName(el);
    if (ic) n.icon = ic;
    return n;
  };
  let idSeq = 0;
  const tag = (el) => {
    if (!el.dataset.w2id) el.dataset.w2id = String(++idSeq);
    return el.dataset.w2id;
  };
  const rootEls = (cfg.roots || []).flatMap((s) => [...document.querySelectorAll(s)]);

  // ---------- visibility ----------
  const vis = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'contents') return true;
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (el.tagName === 'INPUT' && el.type === 'hidden') return false;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0 && !el.matches('select,input,textarea,button')) return false;
    return true;
  };
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return [Math.round(r.x + scrollX), Math.round(r.y + scrollY), Math.round(r.width), Math.round(r.height)];
  };

  // ---------- text helpers ----------
  const MARK = String.fromCharCode(1);
  const MARKS = new RegExp(MARK + '+', 'g');
  const ALNUM_END = /[^\s(\[{]$/u;
  const ALNUM_START = /^[^\s.,;:!?)\]}%]/u;
  const ownText = (el) => norm([...el.childNodes].filter((c) => c.nodeType === 3).map((c) => c.textContent).join(' '));
  const textOf = (el, skip) => {
    let out = '';
    const rec = (n) => {
      if (n.nodeType === 3) {
        out += n.textContent;
        return;
      }
      if (n.nodeType !== 1) return;
      const e = n;
      if (NO_WALK.has(e.tagName.toUpperCase()) || e.tagName.toLowerCase() === 'svg') return;
      if (e.tagName === 'SELECT' || e.tagName === 'TEXTAREA') return;
      if (skip && skip(e)) return;
      if (!vis(e)) return;
      if (e.tagName === 'BR') out += ' ';
      const before = out.length;
      if (ALNUM_END.test(out)) out += MARK;
      for (const c of e.childNodes) rec(c);
      if (out.length > before && ALNUM_END.test(out)) out += MARK;
      if (e.tagName === 'BR' || /^(DIV|P|LI|TR|H[1-6])$/.test(e.tagName)) out += ' ';
    };
    for (const c of el.childNodes) rec(c);
    // MARK sits on an element boundary between two letters or digits: it becomes a space only there
    return norm(out.replace(MARKS, (m, off, str) => (ALNUM_START.test(str[off + m.length] || '') ? ' ' : '')));
  };
  const ttOf = (el) => {
    const t = getComputedStyle(el).textTransform;
    return t && t !== 'none' ? t : '';
  };

  // ---------- classes ----------
  // Tailwind utility classes are not names of the design: only the kit's own component classes are kept
  const KIT_CLASS = /^gc-/;
  const classOf = (el) => [...el.classList].filter((c) => !NOISE_CLASS.has(c) && (!NEXT || KIT_CLASS.test(c))).join(' ');
  const hook = (el) => {
    const out = [];
    for (const [k, v] of Object.entries(el.dataset)) {
      if (k === 'w2id' || k === 'id' || k === 'patientId' || k === 'time' || k === 'date' || k === 'room' || k === 'value' || k === 'patient' || k === 'service') continue;
      out.push(`${k}=${v}`);
    }
    return out.join(' ');
  };

  // ---------- author CSS layout template ----------
  const authorProp = (el, prop) => {
    let found = '';
    const scan = (rules) => {
      for (const r of rules) {
        if (r.type === 1) {
          try {
            if (r.style[prop] && el.matches(r.selectorText)) found = r.style[prop];
          } catch {
            // selector the browser cannot match; ignore
          }
        } else if (r.type === 4 && r.media && window.matchMedia(r.media.mediaText).matches) scan(r.cssRules);
      }
    };
    for (const sh of document.styleSheets) {
      try {
        scan(sh.cssRules);
      } catch {
        // cross-origin sheet
      }
    }
    return el.style[prop] || found;
  };
  const tracks = (v) => (v && v !== 'none' ? v.split(' ').filter(Boolean).length : 0);
  const layOf = (el, nChildren) => {
    const cs = getComputedStyle(el);
    if (cs.display.includes('grid')) {
      const n = tracks(cs.gridTemplateColumns);
      if (n < 2 && nChildren < 2) return null;
      const lay = { d: 'grid', cols: authorProp(el, 'gridTemplateColumns') || cs.gridTemplateColumns, px: cs.gridTemplateColumns, n };
      if (cs.gap && cs.gap !== 'normal' && cs.gap !== '0px') lay.gap = cs.gap;
      return lay;
    }
    if (cs.display.includes('flex') && nChildren >= 2) {
      const row = cs.flexDirection.startsWith('row');
      const lay = { d: 'flex', dir: cs.flexDirection };
      if (cs.flexWrap !== 'nowrap') lay.wrap = true;
      if (cs.justifyContent !== 'normal' && cs.justifyContent !== 'flex-start') lay.jc = cs.justifyContent;
      if (cs.gap && cs.gap !== 'normal' && cs.gap !== '0px') lay.gap = cs.gap;
      if (!row && !el.matches('.main, .content, .app-shell')) lay.stack = true;
      return lay;
    }
    return null;
  };

  // ---------- leaf nodes ----------
  const labelOf = (b) => {
    const t = textOf(b);
    return t || norm(b.getAttribute('aria-label')) || norm(b.getAttribute('title')) || '';
  };
  const variantOf = (el) => {
    const c = el.className || '';
    if (NEXT) {
      const cl = (typeof el.className === 'string' ? el.className : '').split(/\s+/);
      const has = (re) => cl.some((k) => re.test(k));
      if (has(/^bg-brand-(500|600)$/) && has(/^text-(white|surface)$/)) return 'primary';
      if (has(/^(bg|text)-danger/) || has(/^hover:bg-danger/)) return 'danger';
      if (cl.includes('border')) return 'secondary';
      return 'quiet';
    }
    if (/\bbtn-primary\b|\bprimary\b/.test(c)) return 'primary';
    if (/danger|destructive/.test(c)) return 'danger';
    if (/btn-quiet|\bquiet\b/.test(c)) return 'quiet';
    return 'secondary';
  };
  const selectedOf = (el) =>
    el.getAttribute('aria-pressed') === 'true' ||
    ['page', 'true', 'step', 'location'].includes(el.getAttribute('aria-current') || '') ||
    el.getAttribute('aria-selected') === 'true' ||
    el.classList.contains('active') ||
    el.classList.contains('selected');
  const actionNode = (el) => {
    const label = labelOf(el);
    const aria = norm(el.getAttribute('aria-label'));
    const isChip = el.tagName === 'BUTTON' && CHIP_BTN(el);
    const n = { n: isChip ? (el.matches('.tab, [role="tab"], .finance-tabs button, .tabbar button') ? 'tab' : 'chip') : 'action', label };
    if (isChip) n.selected = selectedOf(el);
    else {
      n.variant = variantOf(el);
      if (el.tagName === 'A') n.link = true;
      if (el.getAttribute('href')) n.href = el.getAttribute('href').slice(0, 80);
    }
    if (!textOf(el) && label) n.icon_only = true;
    else if (aria && aria !== label) n.aria = aria;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') n.disabled = true;
    const title = norm(el.getAttribute('title'));
    if (title && title !== label) n.title = title;
    const h = hook(el);
    if (h) n.hook = h;
    const ic = iconName(el);
    if (ic) n.icon = ic;
    if (el.getAttribute('draggable') === 'true') n.draggable = true;
    if (!isChip && selectedOf(el)) n.current = true;
    const c = classOf(el);
    if (c) n.c = c;
    return n;
  };
  const controlLabel = (el) => {
    const parts = [];
    for (const l of el.labels || []) {
      const clone = l.cloneNode(true);
      // a label that also holds a chip (the patient search box) is a wrapper, not the field's name
      if (clone.querySelector('.chip, .badge, .status')) continue;
      clone.querySelectorAll('select,input,textarea,svg,option').forEach((x) => x.remove());
      parts.push(norm(clone.textContent));
    }
    let label = parts.filter(Boolean).join(' ');
    if (!label) label = norm(el.getAttribute('aria-label'));
    return label;
  };
  const fieldNode = (el) => {
    const t = el.tagName.toLowerCase();
    // the Next.js kit's SelectMenu is a button (aria-haspopup=listbox) labelled by a <label for>: a select to the designer
    const menu = NEXT && t === 'button';
    const type = t === 'select' || menu ? 'select' : t === 'textarea' ? 'textarea' : el.type || 'text';
    const n = { n: 'field', type, label: controlLabel(el) };
    const ph = el.getAttribute('placeholder');
    if (ph) n.placeholder = ph;
    if (el.required || el.getAttribute('aria-required') === 'true') n.required = true;
    if (el.disabled) n.disabled = true;
    if (el.readOnly) n.readonly = true;
    for (const a of ['min', 'max', 'step', 'maxlength', 'accept', 'pattern']) if (el.getAttribute(a)) n[a] = el.getAttribute(a);
    if (el.multiple) n.multiple = true;
    if (t === 'select') {
      const opts = [...el.options].map((o) => norm(o.textContent));
      n.options_n = opts.length;
      n.options = opts.length > 12 ? opts.slice(0, 8) : opts;
      const sel = el.selectedOptions[0];
      if (sel) n.default = norm(sel.textContent);
    } else if (menu) {
      n.default = textOf(el);
    } else if (type === 'checkbox' || type === 'radio') {
      n.checked = el.checked;
      if (el.name) n.group = el.name;
    } else if (type === 'file') {
      // nothing else
    } else if (el.value) {
      n.default = el.value.length > 80 ? el.value.slice(0, 80) + '…' : el.value;
    }
    if (el.id) n.id = el.id;
    if (!n.label && (n.placeholder || el.name)) n.label = '';
    return n;
  };

  // ---------- categorised collectors (independent of the tree; used by the coverage check) ----------
  const lists = { actions: [], fields: [], chips_tabs: [], badges_status: [], kpis: [], notices: [], empty_states: [], tables: [], headings: [] };
  const seen = new WeakSet();
  const consumed = new WeakSet();
  // data rows after the first one of a table or a repeated list: counted, not listed (their texts are demo data)
  const skipData = new WeakSet();

  // ---------- walking ----------
  const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);
  const text = (el, flags) => {
    const n = { n: 'text', t: textOf(el) };
    withIcon(n, el);
    const tt = ttOf(el);
    if (tt) n.tt = tt;
    Object.assign(n, flags || {});
    return n;
  };

  function badgeNode(el) {
    const n = { n: 'badge', t: textOf(el), c: classOf(el) };
    const cs = getComputedStyle(el);
    n.bg = cs.backgroundColor;
    n.color = cs.color;
    return n;
  }

  function kpiNode(el) {
    const blocks = [];
    const actions = [];
    const rec = (e) => {
      for (const c of e.children) {
        if (!vis(c) || NO_WALK.has(c.tagName.toUpperCase()) || c.tagName.toLowerCase() === 'svg') continue;
        if (c.tagName === 'BUTTON' || (c.tagName === 'A' && c.getAttribute('href'))) {
          seen.add(c);
          if (!(c.matches(KPI_SEL) && c === el)) actions.push(actionNode(c));
          continue;
        }
        if (ownText(c)) {
          const fs = parseFloat(getComputedStyle(c).fontSize);
          blocks.push({ t: textOf(c, (x) => x.tagName === 'BUTTON'), fs });
        } else rec(c);
      }
    };
    rec(el);
    if (el.tagName === 'BUTTON') {
      // a button that is itself a kpi (crm-kpi): its label is the whole content
    }
    let value = null;
    let vi = -1;
    blocks.forEach((b, i) => {
      if (!value || b.fs > value.fs) {
        value = b;
        vi = i;
      }
    });
    const label = blocks.filter((_, i) => i < vi).map((b) => b.t).join(' ') || (vi > 0 ? '' : '');
    const hint = blocks.filter((_, i) => i > vi).map((b) => b.t).join(' · ');
    const n = { n: 'kpi', label: label || (blocks.length > 1 && vi === 0 ? '' : label), value: value ? value.t : '', c: classOf(el) };
    withIcon(n, el);
    if (vi === 0 && blocks.length > 1) {
      // value first, caption after (crm-reception-stats, crm-stages): the next block is the label
      n.label = blocks[1].t;
      n.hint = blocks.slice(2).map((b) => b.t).join(' · ') || undefined;
      if (!n.hint) delete n.hint;
    } else if (hint) n.hint = hint;
    if (el.tagName === 'BUTTON') {
      n.is_button = true;
      const h = hook(el);
      if (h) n.hook = h;
    }
    if (actions.length) n.actions = actions;
    return n;
  }

  function tableNode(el) {
    const cols = [...el.querySelectorAll('thead th, thead td')].filter(vis).map((c) => norm(c.textContent));
    const rows = [...el.querySelectorAll('tbody tr')].filter(vis);
    const n = { n: 'table', c: classOf(el), cols };
    const cap = el.querySelector('caption');
    if (cap) n.caption = norm(cap.textContent);
    n.rows = rows.length;
    if (rows.length === 1 && rows[0].children.length === 1 && rows[0].children[0].colSpan > 1) {
      n.empty = norm(rows[0].textContent);
      n.rows = 0;
    } else if (rows.length) {
      const first = rows[0];
      rows.slice(1).forEach((r) => skipData.add(r));
      n.first = [...first.children].filter(vis).map((c) => {
        const cell = [];
        collect(c, cell);
        return cell;
      });
      n.first_text = [...first.children].filter(vis).map((c) => trunc(textOf(c), 80));
      if (first.matches('.clickable') || first.getAttribute('data-patient')) n.row_click = true;
      const variants = variantsOf(rows);
      if (variants) n.variants = variants;
    }
    const foot = el.querySelector('tfoot');
    if (foot && vis(foot)) n.foot = trunc(norm(foot.textContent), 160);
    lists.tables.push({ id: tag(el), cols, rows: n.rows, first: n.first_text || [] });
    n.box = box(el);
    return n;
  }

  function variantsOf(els) {
    const acts = new Map();
    const badges = new Map();
    const links = new Map();
    for (const e of els) {
      e.querySelectorAll('button, a[href], input[type="button"], input[type="submit"]').forEach((b) => {
        if (!vis(b)) return;
        const l = labelOf(b);
        const h = hook(b);
        // buttons that share a hook (data-ops="new", data-crm="task") are one action with data in its label
        // the first data-* pair is the kind of action; the others (ids) are data
        const key = (h ? h.split(' ')[0] : l) + '|' + variantOf(b);
        if (b.matches('.crm-name, [data-patient], .linked-link')) links.set(key, (links.get(key) || 0) + 1);
        else {
          const cur = acts.get(key) || { label: l, variant: variantOf(b), hook: h ? h.split(' ')[0] : '', count: 0, labels: new Set() };
          cur.count++;
          cur.labels.add(l);
          acts.set(key, cur);
        }
      });
      e.querySelectorAll(BADGE_SEL).forEach((b) => {
        if (!vis(b)) return;
        const key = textOf(b) + '|' + classOf(b);
        badges.set(key, (badges.get(key) || 0) + 1);
      });
    }
    const out = {};
    if (acts.size) out.actions = [...acts.values()].map((a) => ({ label: a.label, variant: a.variant, ...(a.hook ? { hook: a.hook } : {}), count: a.count, ...(a.labels.size > 1 ? { distinct: a.labels.size } : {}) }));
    if (badges.size) out.badges = [...badges].map(([k, c]) => ({ t: k.split('|')[0], c: k.split('|')[1], count: c }));
    if (links.size) out.links = links.size;
    return Object.keys(out).length ? out : null;
  }

  function collect(el, into) {
    for (const k of walkNode(el)) into.push(k);
  }

  function repeatKey(el) {
    for (const k of REPEAT) if (el.classList.contains(k)) return k;
    return '';
  }

  function walkChildren(el) {
    const out = [];
    const kids = [...el.childNodes];
    for (let i = 0; i < kids.length; i++) {
      const c = kids[i];
      if (c.nodeType === 3) {
        const t = norm(c.textContent);
        if (t) out.push({ n: 'text', t, loose: true });
        continue;
      }
      if (c.nodeType !== 1) continue;
      // the phone web (Patient Mobile, group WI) is short and every row is content (a timeline of events, a list of invoices): nothing is collapsed there
      const key = c.closest('.mobile-app') ? '' : repeatKey(c);
      if (key) {
        // collapse a run of >= REPEAT_MIN data-row siblings: show the first, count the rest
        let j = i;
        const run = [];
        while (j < kids.length && (kids[j].nodeType !== 1 || repeatKey(kids[j]) === key || !norm(kids[j].textContent) && !kids[j].children.length)) {
          if (kids[j].nodeType === 1 && repeatKey(kids[j]) === key && vis(kids[j])) run.push(kids[j]);
          j++;
        }
        if (run.length >= REPEAT_MIN) {
          const first = walkNode(run[0]);
          const node = { n: 'list', of: key, count: run.length, item: first };
          const variants = variantsOf(run.slice(1));
          if (variants) node.variants = variants;
          const classes = [...new Set(run.flatMap((r) => [...r.classList].filter((x) => x !== key)))].filter((x) => !NOISE_CLASS.has(x));
          if (classes.length) node.classes = classes.slice(0, 8);
          if (key === 'drop-slot') {
            node.sample_aria = norm(run[0].getAttribute('aria-label'));
            node.item = [];
          }
          for (const r of run) seen.add(r);
          (key === 'drop-slot' ? run : run.slice(1)).forEach((r) => skipData.add(r));
          out.push(node);
          i = j - 1;
          continue;
        }
      }
      for (const k of walkNode(c)) out.push(k);
    }
    return out;
  }

  function inlineOnly(el) {
    for (const c of el.children) {
      if (!vis(c)) continue;
      if (NO_WALK.has(c.tagName.toUpperCase()) || c.tagName.toLowerCase() === 'svg') continue;
      if (!INLINE.has(c.tagName)) return false;
      if (c.tagName === 'A' && (c.getAttribute('href') || c.classList.length)) return false;
      if ([...c.classList].some((k) => !['muted', 'ops-muted', 'ui-icon', 'icon-wrap'].includes(k))) return false;
      if (c.matches(BADGE_SEL + ', button, .avatar, .progress, .dot')) return false;
      if (c.querySelector('button, input, select, textarea, a[href], table, img')) return false;
      if (c.tagName === 'SPAN' && c.matches('.icon-wrap')) continue;
    }
    return true;
  }

  function parts(el) {
    // segments of an inline-only container, marking strong / small
    const out = [];
    const rec = (n, mark) => {
      if (n.nodeType === 3) {
        const t = norm(n.textContent);
        if (t) out.push(mark ? [t, mark] : [t]);
        return;
      }
      if (n.nodeType !== 1) return;
      const e = n;
      if (!vis(e) || e.tagName.toLowerCase() === 'svg') return;
      if (e.tagName === 'BR') return;
      const m = e.tagName === 'SMALL' || e.classList.contains('muted') || e.classList.contains('ops-muted') ? 'small' : e.tagName === 'STRONG' || e.tagName === 'B' ? 'strong' : mark;
      for (const c of e.childNodes) rec(c, m);
    };
    for (const c of el.childNodes) rec(c, '');
    return out;
  }

  function walkNode(el) {
    if (!el || el.nodeType !== 1) return [];
    if (seen.has(el)) return [];
    const T = el.tagName.toUpperCase();
    if (el.tagName.toLowerCase() === 'svg' && el.classList.contains('ui-icon') && vis(el) && !el.closest('button, a[href]')) return [{ n: 'icon', name: iconName(el) }];
    // Patient Mobile (WI): the illustrative faces are svg role=img whose aria-label is their only text
    if (el.tagName.toLowerCase() === 'svg' && el.getAttribute('role') === 'img' && el.closest('.mobile-app') && vis(el)) return [{ n: 'img', alt: el.getAttribute('aria-label') || '', box: box(el)[2] + 'x' + box(el)[3] }];
    if (NO_WALK.has(T) || el.tagName.toLowerCase() === 'svg') return [];
    if (!vis(el)) return [];
    seen.add(el);
    // Next.js: a spinner is a role=status element whose only text is its aria-label (the loading frame, WL15)
    if (NEXT && el.getAttribute('role') === 'status' && !textOf(el) && el.getAttribute('aria-label')) return [{ n: 'progress', pct: '', aria: el.getAttribute('aria-label') }];
    const cls = el.classList;
    const lc = el.tagName.toLowerCase();

    // ---- controls ----
    if (T === 'BUTTON' || (T === 'A' && el.getAttribute('href') !== null) || el.getAttribute('role') === 'button' || (T === 'INPUT' && ['button', 'submit', 'reset'].includes(el.type))) {
      if (T === 'INPUT') {
        const n = { n: 'action', label: el.value, variant: variantOf(el) };
        lists.actions.push(n);
        return [n];
      }
      if (el.matches(KPI_SEL)) {
        const k = kpiNode(el);
        lists.kpis.push(k);
        return [k];
      }
      const n = actionNode(el);
      if (n.n === 'action') lists.actions.push(n);
      else lists.chips_tabs.push(n);
      // a button that holds status badges or avatars keeps them (patient name + chip)
      return [n];
    }
    if (T === 'INPUT' || T === 'SELECT' || T === 'TEXTAREA') {
      if (consumed.has(el)) return [];
      consumed.add(el);
      const n = fieldNode(el);
      lists.fields.push(n);
      return [n];
    }
    if (T === 'LABEL') {
      const next = el.nextElementSibling;
      // a label without `for` labels the control right after it (<div class="field"><label>…</label><select>)
      const ctl = el.control || el.querySelector('input,select,textarea') || (next && next.matches('input,select,textarea') ? next : null);
      const wrapsMore = ctl && el.contains(ctl) && [...el.children].some((c) => c !== ctl && !c.contains(ctl) && vis(c) && textOf(c));
      if (ctl && vis(ctl) && !wrapsMore && !(ctl.tagName === 'INPUT' && ctl.type === 'file')) {
        if (consumed.has(ctl)) return [];
        consumed.add(ctl);
        seen.add(ctl);
        const n = fieldNode(ctl);
        if (!n.label) n.label = textOf(el);
        lists.fields.push(n);
        return [n];
      }
      if (ctl && !wrapsMore && ctl.tagName === 'INPUT' && ctl.type === 'file') {
        const n = fieldNode(ctl);
        n.label = textOf(el) || n.label;
        n.n = 'field';
        consumed.add(ctl);
        seen.add(ctl);
        lists.fields.push(n);
        return [n];
      }
      if (el.control === null && el.htmlFor === '' && !textOf(el)) return [];
    }
    if (T === 'IMG') {
      return [{ n: 'img', alt: el.getAttribute('alt') || '', box: box(el)[2] + 'x' + box(el)[3] }];
    }
    if (T === 'CANVAS') return [{ n: 'img', alt: 'canvas', box: box(el)[2] + 'x' + box(el)[3] }];

    // ---- specials by class / tag ----
    if (T === 'TABLE') return [tableNode(el)];
    if (el.matches(KPI_SEL) && !el.closest('table')) {
      const k = kpiNode(el);
      lists.kpis.push(k);
      mark(el);
      return [k];
    }
    if (el.matches('.icon-wrap, .ico, .care-icon, .doc-icon, .step-icon, .metric-symbol') && !textOf(el) && !hasCtl(el) && el.querySelector('svg')) return [{ n: 'icon', name: iconName(el) }];
    if (el.matches('.avatar, .patient-avatar, .resource-avatar')) {
      const t = textOf(el);
      return [{ n: 'avatar', t, c: classOf(el) }];
    }
    // Patient Mobile (WI): the session rail (one segment per session) and the progress bar carry their text in aria-label
    if (el.matches('.session-rail') && el.closest('.mobile-app')) {
      const segs = [...el.children];
      const done = segs.filter((s) => s.classList.contains('complete')).length;
      return [{ n: 'progress', pct: segs.length ? Math.round((done / segs.length) * 100) + '%' : '', segments: segs.length, done, aria: el.getAttribute('aria-label') || '' }];
    }
    if (el.matches('.progress, .bar') && !textOf(el)) {
      const i = el.querySelector('i');
      const aria = el.closest('.mobile-app') ? el.getAttribute('aria-label') || '' : '';
      return [{ n: 'progress', pct: i ? i.style.width || '' : '', ...(aria ? { aria } : {}) }];
    }
    if (el.matches(NOTICE_SEL) && textOf(el)) {
      const nn = { n: 'notice', t: textOf(el), c: classOf(el) };
      const role = el.getAttribute('role');
      if (role) nn.role = role;
      const tt = ttOf(el);
      if (tt) nn.tt = tt;
      const acts = [...el.querySelectorAll('button, a[href]')].filter(vis);
      if ([...el.querySelectorAll('input:not([type="hidden"]), select, textarea')].some(vis)) {
        // a box that holds fields (studio zoom and slider): keep the whole content, not only its text
        mark(el);
        nn.children = walkChildren(el);
        lists.notices.push(nn);
        return [nn];
      }
      if (acts.length) {
        nn.t = textOf(el, (x) => x.tagName === 'BUTTON');
        nn.actions = acts.map((a) => {
          seen.add(a);
          const an = actionNode(a);
          lists.actions.push(an);
          return an;
        });
      }
      mark(el);
      lists.notices.push(nn);
      return [nn];
    }
    if (el.matches('p.empty, .empty') && textOf(el)) {
      const e = { n: 'empty', t: textOf(el) };
      if (hasCtl(el)) e.children = walkChildren(el);
      lists.empty_states.push(e);
      return [e];
    }
    if (el.matches(BADGE_SEL) && !el.matches('.priority') && el.children.length === 0 && textOf(el)) {
      const b = badgeNode(el);
      lists.badges_status.push(b);
      return [b];
    }
    if (el.matches(BADGE_SEL) && textOf(el) && !el.querySelector('button, a[href], input, select')) {
      const b = badgeNode(el);
      lists.badges_status.push(b);
      return [b];
    }
    if (el.matches('.eyebrow') && textOf(el)) return [text(el, { eyebrow: true })];
    if (/^H[1-6]$/.test(T) || el.matches('.page-title, .panel-title, .section-label, .room-heading, .time-heading, .week-title') && !el.children.length) {
      const level = /^H[1-6]$/.test(T) ? +T[1] : el.matches('.page-title') ? 1 : 3;
      const t = textOf(el, (x) => x.tagName === 'SMALL');
      const sm = el.querySelector('small');
      const h = withIcon({ n: 'heading', level, t: t || textOf(el) }, el);
      if (sm && vis(sm)) h.sub = textOf(sm);
      const tt = ttOf(el);
      if (tt) h.tt = tt;
      lists.headings.push({ level, t: h.t });
      if (h.t) {
        if (hasCtl(el)) h.children = walkChildren(el);
        return [h];
      }
    }
    if (el.matches('.panel-title') && el.querySelector('small')) {
      const t = textOf(el, (x) => x.tagName === 'SMALL');
      const h = { n: 'heading', level: 3, t, sub: textOf(el.querySelector('small')) };
      lists.headings.push({ level: 3, t });
      return [h];
    }
    if (T === 'DL' && !hasCtl(el)) {
      const items = [];
      for (const c of el.children) {
        if (c.tagName === 'DT') items.push([textOf(c), '']);
        else if (c.tagName === 'DD' && items.length) items[items.length - 1][1] = textOf(c);
        else if (c.tagName === 'DIV') {
          const dt = c.querySelector('dt');
          const dd = c.querySelector('dd');
          if (dt) items.push([textOf(dt), dd ? textOf(dd) : '']);
        }
      }
      return [{ n: 'facts', items }];
    }
    if (el.matches('.fact') && el.children.length >= 2 && !hasCtl(el)) {
      const lab = el.querySelector('label, span, small');
      const val = el.querySelector('strong, b');
      if (lab && val) return [{ n: 'fact', label: textOf(lab), value: textOf(val) }];
    }
    if (T === 'HR') return [{ n: 'rule' }];
    if (T === 'DETAILS') {
      const sm = [...el.children].find((c) => c.tagName === 'SUMMARY');
      if (sm) seen.add(sm);
      const dn = { n: 'details', summary: sm ? textOf(sm) : '', open: el.open, children: walkChildren(el) };
      if (sm) lists.actions.push({ n: 'action', label: dn.summary, variant: 'secondary', summary: true });
      return [dn];
    }
    if (el.matches('.dot') && !textOf(el)) return [];

    // ---- inline-only text container ----
    if (inlineOnly(el) && textOf(el) && !CARD_SEL_MATCH(el)) {
      const p = parts(el);
      const n = { n: 'text', t: textOf(el) };
      if (p.length > 1 && p.some((x) => x[1])) n.p = p;
      else if (p.length === 1 && p[0][1]) n.mark = p[0][1];
      else if (T === 'STRONG' || T === 'B' || T === 'H4') n.mark = 'strong';
      else if (T === 'SMALL') n.mark = 'small';
      const tt = ttOf(el);
      if (tt) n.tt = tt;
      const c = classOf(el);
      if (c && !el.matches('div, p, span, small, strong, li')) n.c = c;
      else if (c) n.c = c;
      return [n];
    }

    // ---- containers ----
    let kids = walkChildren(el);
    if (!kids.length) {
      return [];
    }
    const c = classOf(el);
    if (T === 'FORM') {
      const n = { n: 'form', id: el.id || undefined, c: c || undefined, children: kids };
      return [n];
    }
    if (el.matches(CARD_SEL)) {
      const n = { n: 'card', c, box: box(el), children: kids };
      if (T === 'SECTION' || T === 'ASIDE' || T === 'ARTICLE') n.tag = lc;
      const role = el.getAttribute('role');
      if (role) n.role = role;
      const ariaLabel = el.getAttribute('aria-label');
      if (ariaLabel) n.aria = ariaLabel;
      const lay = layOf(el, kids.length);
      if (lay && !lay.stack) n.lay = lay;
      n.w2 = tag(el);
      return [n];
    }
    if (T === 'NAV') return [{ n: 'nav', c: c || undefined, aria: el.getAttribute('aria-label') || undefined, children: kids }];
    if (T === 'UL' || T === 'OL') return [{ n: 'list_el', ordered: T === 'OL', children: kids }];
    if (T === 'LI') return kids.length === 1 ? kids : [{ n: 'li', children: kids }];
    const lay = layOf(el, kids.length);
    if (lay && !lay.stack) {
      return [{ n: 'group', c: c || undefined, lay, box: box(el), w2: tag(el), children: kids }];
    }
    if (el.matches('header, aside, main, footer, section, article') && kids.length > 1) {
      return [{ n: 'group', tag: lc, c: c || undefined, box: box(el), w2: tag(el), children: kids }];
    }
    if (el.matches('.field') && kids.length > 1) return [{ n: 'group', c: 'field', children: kids }];
    return kids;
  }

  function CARD_SEL_MATCH(el) {
    return el.matches(CARD_SEL);
  }
  function mark(el) {
    seen.add(el);
  }

  // ---------- run ----------
  const tree = [];
  for (const r of rootEls) {
    if (!vis(r)) continue;
    // the root itself is a container: keep its own wrapper info (modal, content)
    const kids = walkNode(r);
    // #main-content and body are wrappers, not UI: their children are the tree; a dialog or toast keeps its own node
    if (r.matches('#main-content, #main, body') && kids.length === 1 && Array.isArray(kids[0].children)) tree.push(...kids[0].children);
    else tree.push(...kids);
  }
  // visible toast anywhere (a state of its own, WA4)
  if (cfg.mode !== 'toast') {
    for (const t of document.querySelectorAll('.toast')) {
      if (vis(t) && !t.dataset.w2id) tree.push(...walkNode(t));
    }
  }

  // ---------- every visible text must be in the tree: collect the raw list for the node-side coverage check ----------
  const texts = [];
  const skipTexts = (n) => {
    const p = n.parentElement;
    if (!p) return true;
    if (p.closest('select, textarea, script, style, svg, template, noscript, option')) return true;
    return !vis(p) || !!p.closest('[hidden]');
  };
  for (const r of rootEls) {
    const walker = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      if (skipTexts(n)) continue;
      let hiddenAncestor = false;
      for (let e = n.parentElement; e && e !== r.parentElement; e = e.parentElement) {
        if (!vis(e)) {
          hiddenAncestor = true;
          break;
        }
      }
      if (hiddenAncestor) continue;
      let data = false;
      for (let e = n.parentElement; e; e = e.parentElement) if (skipData.has(e)) data = true;
      if (data) continue;
      const t = norm(n.textContent);
      if (t) texts.push(t);
    }
  }

  // ---------- every visible control must have become a node (field, action, tab, chip, kpi button) ----------
  const unseen = [];
  for (const r of rootEls) {
    for (const c of r.querySelectorAll(CTRL)) {
      if (!vis(c) || seen.has(c) || consumed.has(c)) continue;
      // a button inside a hidden responsive twin (the phone cards at desktop width) is not a control of this frame
      if (NEXT && !c.getClientRects().length) continue;
      let data = false;
      for (let e = c.parentElement; e; e = e.parentElement) if (skipData.has(e)) data = true;
      if (data || c.closest('details:not([open])') && c.tagName !== 'SUMMARY') continue;
      if (c.tagName === 'INPUT' && c.type === 'file' && c.closest('label, .upload-box')) continue;
      unseen.push(c.tagName.toLowerCase() + (c.id ? '#' + c.id : '') + ' ' + trunc(textOf(c) || c.getAttribute('aria-label') || c.getAttribute('name') || '', 60));
    }
  }

  // ---------- computed styles of every visible element under the roots ----------
  const raw = { color: {}, bg: {}, border: {}, radius: {}, font: {}, shadow: {}, family: {} };
  const bump = (o, k, who) => {
    if (!o[k]) o[k] = { n: 0, ex: who };
    o[k].n++;
  };
  const px = (v) => parseFloat(v) || 0;
  const all = [];
  for (const r of rootEls) {
    all.push(r, ...r.querySelectorAll('*'));
  }
  for (const el of all) {
    if (NO_WALK.has(el.tagName.toUpperCase()) || el.closest('svg') || !vis(el)) continue;
    const cs = getComputedStyle(el);
    const who = el.tagName.toLowerCase() + (el.classList.length ? '.' + [...el.classList].slice(0, 2).join('.') : '');
    if (ownText(el)) {
      bump(raw.color, cs.color, who);
      bump(raw.font, cs.fontSize, who);
      bump(raw.family, cs.fontFamily.split(',')[0].replace(/["']/g, '').trim(), who);
    }
    if (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent') bump(raw.bg, cs.backgroundColor, who);
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
      if (px(cs['border' + side + 'Width']) > 0 && cs['border' + side + 'Style'] !== 'none') {
        bump(raw.border, cs['border' + side + 'Color'], who);
        break;
      }
    }
    const rad = cs.borderTopLeftRadius;
    if (px(rad) > 0) bump(raw.radius, rad, who);
    if (cs.boxShadow && cs.boxShadow !== 'none') bump(raw.shadow, cs.boxShadow, who);
    if (el.tagName === 'svg') continue;
  }

  // ---------- regions ----------
  const regions = [];
  const addRegion = (name, sel) => {
    const el = document.querySelector(sel);
    if (el && vis(el)) {
      regions.push({ name, sel, box: box(el) });
    }
  };
  if (NEXT) {
    addRegion('sidebar', 'aside');
    addRegion('topbar', 'header');
    addRegion('content', '#main');
    addRegion('modal', '[role="dialog"]');
  } else {
    addRegion('sidebar', '.sidebar');
    addRegion('topbar', '.topbar');
    addRegion('content', '#main-content');
    addRegion('modal', '.modal-backdrop .modal');
    addRegion('page-heading', '.page-heading');
  }
  const shell = {};
  if (NEXT) {
    const side = document.querySelector('aside');
    if (side && vis(side)) {
      shell.nav_items = [...side.querySelectorAll('nav a, nav [aria-disabled="true"]')].filter(vis).map((b) => textOf(b));
      const cur = side.querySelector('a[aria-current]');
      if (cur) shell.active = textOf(cur);
    }
    const crumbs = document.querySelector('header nav');
    if (crumbs && vis(crumbs)) shell.breadcrumbs = textOf(crumbs);
    shell.body = { page: '', role: '', patient_tab: '' };
    shell.title = document.title;
    return { tree, lists, texts, raw, regions, shell, unseen, tagged: idSeq, url: location.pathname + location.search };
  }
  const nav = document.querySelector('.sidebar');
  if (nav && vis(nav)) {
    shell.nav_items = [...nav.querySelectorAll('.nav-item')].filter(vis).map((b) => textOf(b));
    const act = nav.querySelector('.nav-item.active, .nav-item[aria-current]');
    if (act) shell.active = textOf(act);
  }
  const bc = document.querySelector('.breadcrumbs');
  if (bc && vis(bc)) shell.breadcrumbs = textOf(bc);
  const acct = document.querySelector('#staff-account');
  if (acct) shell.account = norm(acct.selectedOptions[0] ? acct.selectedOptions[0].textContent : '');
  shell.body = { page: document.body.dataset.page || '', role: document.body.dataset.staffRole || '', patient_tab: document.body.dataset.patientTab || '' };
  shell.title = document.title;

  return { tree, lists, texts, raw, regions, shell, unseen, tagged: idSeq, url: location.pathname + location.search };
}

// ---- layout probe: same tagged elements at another viewport ----
function probeInPage() {
  const out = { els: {}, overflow_x: 0, texts: [], vw: innerWidth };
  const norm = (s) => (s || '').replace(/[ \s]+/g, ' ').trim();
  const vis = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return !(r.width === 0 && r.height === 0);
  };
  const tracks = (v) => (v && v !== 'none' ? v.split(' ').filter(Boolean).length : 0);
  for (const el of document.querySelectorAll('[data-w2id]')) {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const o = { v: vis(el), d: cs.display, w: Math.round(r.width) };
    if (cs.display.includes('grid')) o.cols = tracks(cs.gridTemplateColumns);
    if (cs.display.includes('flex')) {
      o.dir = cs.flexDirection;
      o.wrap = cs.flexWrap !== 'nowrap';
    }
    const tbl = el.matches('table') ? el : null;
    if (tbl) {
      const th = tbl.querySelector('thead');
      o.thead = th ? vis(th) : false;
    }
    out.els[el.dataset.w2id] = o;
  }
  for (const sel of ['.sidebar', '.topbar', '.main', '#main-content', '.modal-backdrop .modal', '.tabbar', '.page-heading', 'aside', 'header', '#main', '[role="dialog"]']) {
    const el = document.querySelector(sel);
    if (el) {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      out.els['sel:' + sel] = { v: vis(el), d: cs.display, w: Math.round(r.width), pos: cs.position };
    }
  }
  out.overflow_x = Math.max(0, document.documentElement.scrollWidth - innerWidth);
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  const set = new Set();
  while ((n = walker.nextNode())) {
    const p = n.parentElement;
    if (!p || p.closest('script,style,svg,select,textarea,option,template')) continue;
    let ok = true;
    for (let e = p; e && e !== document.body; e = e.parentElement) {
      if (!vis(e)) {
        ok = false;
        break;
      }
    }
    const t = norm(n.textContent);
    if (ok && t) set.add(t);
  }
  out.texts = [...set];
  return out;
}

module.exports = { extractInPage, probeInPage };
