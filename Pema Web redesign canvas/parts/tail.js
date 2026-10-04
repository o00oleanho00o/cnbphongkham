// tail.js: groups and validation (framework part, frozen after W3a). GROUP_DEFS is written by web-canvas-build.cjs from
// design-specs/web/inventory.json; WA ... WH are the group parts.
const PARTS = { WA, WB, WC, WD, WE, WF, WG, WH };
const groups = GROUP_DEFS.map(g => ({ ...g, screens: PARTS[g.code] }));

// A block that the markup cannot draw, a container nested too deep or a wrong id fails here, in the Node
// loader and in the viewer alike, with the screen id in the message.
const KIND_INLINE = ['txt', 'btn', 'badge', 'avatar', 'icon', 'chip', 'prog'];
const KIND_LEAF = ['h', 'pageHead', 'hero', 'kpis', 'stat', 'chips', 'tags', 'tabs', 'notice', 'facts', 'field', 'table', 'empty', 'bars', 'timeline', 'list', 'board', 'weekGrid', 'photos', 'a5', 'img', 'legend', 'sp', 'hr', 'code'];
const KIND_CONT = ['stack', 'row', 'grid', 'card', 'box', 'disc'];
const MAX_CONTAINER_LEVEL = 3;
const checkInline = (id, where, items) => (items || []).forEach(x => { if (!isNode(x) || !KIND_INLINE.includes(x.k)) throw new Error(`${id}: ${where} accepts only inline blocks (${KIND_INLINE.join(', ')}), got ${x && x.k}`); });
const checkNode = (id, n, level) => {
  if (!isNode(n)) throw new Error(`${id}: a block is not a node: ${JSON.stringify(n)}`);
  if (KIND_CONT.includes(n.k)) {
    if (level > MAX_CONTAINER_LEVEL) throw new Error(`${id}: ${n.k} nested too deep (containers go 4 levels: container > container > container > container > leaf)`);
    if (n.k === 'card') checkInline(id, 'card.aside', n.aside);
    n.kids.forEach(c => checkNode(id, c, level + 1));
    return;
  }
  if (!KIND_LEAF.includes(n.k) && !KIND_INLINE.includes(n.k)) throw new Error(`${id}: unknown block kind ${n.k}`);
  if (n.k === 'pageHead' || n.k === 'hero' || n.k === 'notice' || n.k === 'empty') checkInline(id, n.k + '.actions', n.actions);
  if (n.k === 'kpis') n.items.forEach(i => checkInline(id, 'kpis item actions', i.actions));
  if (n.k === 'list') n.items.forEach(i => checkInline(id, 'list item actions', i.actions));
  if (n.k === 'table') n.rows.forEach(r => r.cells.forEach(c => checkInline(id, 'table cell', c.items)));
};
const seen = {};
groups.forEach(g => g.screens.forEach(sc => {
  if (!new RegExp('^' + g.code + '\\d+$').test(sc.id)) throw new Error(`${sc.id}: id must be ${g.code}<number> in group ${g.code}`);
  if (seen[sc.id]) throw new Error(`${sc.id}: defined twice`);
  seen[sc.id] = true;
  sc.frames.forEach(f => { if (!SIZES[f.size]) throw new Error(`${sc.id}: unknown frame ${f.size}`); });
  sc.blocks.forEach(b => checkNode(sc.id, b, 0));
  sc.dialog.blocks.forEach(b => checkNode(sc.id, b, 0));
  checkInline(sc.id, 'dialog footer', sc.dialog.footer);
}));
return groups;
