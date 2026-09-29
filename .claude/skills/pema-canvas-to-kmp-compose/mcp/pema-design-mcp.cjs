#!/usr/bin/env node
// MCP server "pema-design" (stdio, no dependencies): per-screen design/conversion specs of the Pema
// app, the way Stitch / Claude Design expose the prompt behind each screen.
//
//   tools     list_screens · get_screen · get_screen_image · get_block_catalog · record_note · regenerate_specs
//   prompts   port_screen(id) + one prompt per screen ("A1" … "K3")
//   resources pema-design://screens/<ID> · pema-design://blocks · pema-design://index
//
// Data is built live from the canvas, the KMP/Flutter code and design-specs/notes.json
// (see ../scripts/specs-lib.cjs), so it never goes stale. Register: see design-specs/README.md.
const fs = require('fs');
const path = require('path');
const lib = require('../scripts/specs-lib.cjs');

const SERVER = { name: 'pema-design', version: '1.0.0' };
const SUPPORTED = ['2025-06-18', '2025-03-26', '2024-11-05'];

let cache = { at: 0, model: null };
function model() {
  if (!cache.model || Date.now() - cache.at > 3000) cache = { at: Date.now(), model: lib.buildModel() };
  return cache.model;
}
const invalidate = () => (cache = { at: 0, model: null });

function findScreen(id) {
  const s = model().screens.find((x) => x.id.toLowerCase() === String(id || '').trim().toLowerCase());
  if (!s) throw new Error(`No screen "${id}". Use list_screens to see the codes (A1 … K3).`);
  return s;
}

const text = (t) => ({ content: [{ type: 'text', text: t }] });

// ---------- tools ----------
const TOOLS = [
  {
    name: 'list_screens',
    description: 'List the Pema design canvas screens (code, name, group, Flutter/web logic source, KMP composable, port status). Filter by group (A–K) or keyword.',
    inputSchema: {
      type: 'object',
      properties: {
        group: { type: 'string', description: 'Group code A–K, e.g. "I"' },
        query: { type: 'string', description: 'Search code, name, note and on-screen text' },
      },
    },
    run: ({ group, query } = {}) => {
      const q = String(query || '').toLowerCase();
      const rows = model().screens
        .filter((s) => !group || s.group === String(group).toUpperCase())
        .filter((s) => !q || [s.id, s.name, s.note, ...s.texts].join(' ').toLowerCase().includes(q))
        .map((s) => `${s.id} · ${s.name} — ${s.source.kind === 'web' ? 'web' : 'Flutter'} → ${s.kmp.composable || '—'} (${s.kmp.module || '—'}) ${s.status === 'ported' ? '✓' : '✗'}`);
      return text(rows.length ? rows.join('\n') : 'No matching screens.');
    },
  },
  {
    name: 'get_screen',
    description: 'Full spec of one screen, to build/port it without re-reading the web/canvas: logic source, route + KMP file, block → Compose layout, required text, business rules, accepted differences, known gotchas and a prompt.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', description: 'Screen code, e.g. "I2"' },
        format: { type: 'string', enum: ['markdown', 'json'], description: 'Default markdown' },
      },
      required: ['id'],
    },
    run: ({ id, format }) => {
      const s = findScreen(id);
      return text(format === 'json' ? JSON.stringify(s, null, 2) : lib.screenMarkdown(s, model()));
    },
  },
  {
    name: 'get_screen_image',
    description: 'PNG of a screen: "canvas" = design reference image (pema-kmp/design-ref), "compare" = canvas | Compose side-by-side from jvmTest.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', description: 'Screen code' },
        kind: { type: 'string', enum: ['canvas', 'compare'], description: 'Default canvas' },
      },
      required: ['id'],
    },
    run: ({ id, kind }) => {
      const s = findScreen(id);
      if (kind === 'compare' && !s.kmp.shotImage) throw new Error(`${s.id} has no shot test yet.`);
      const file = kind === 'compare' ? path.join(lib.ROOT, s.kmp.shotImage) : path.join(lib.REF_DIR, `${s.id}.png`);
      if (!fs.existsSync(file)) {
        const task = s.kmp.module.replace(/^pema-kmp\//, ':').replace(/\//g, ':');
        throw new Error(kind === 'compare'
          ? `${lib.rel(file)} missing — run .\\gradlew.bat ${task}:jvmTest in pema-kmp`
          : `${lib.rel(file)} missing — run .\\gradlew.bat canvasRefs in pema-kmp`);
      }
      return {
        content: [
          { type: 'image', data: fs.readFileSync(file).toString('base64'), mimeType: 'image/png' },
          { type: 'text', text: `${s.id} · ${s.name} — ${lib.rel(file)}` },
        ],
      };
    },
  },
  {
    name: 'get_block_catalog',
    description: 'Lookup table of canvas block helpers (h, t, n, fc, fl, dd, chips…) → core:ui Compose components.',
    inputSchema: { type: 'object', properties: {} },
    run: () => text(lib.blocksMarkdown()),
  },
  {
    name: 'record_note',
    description: 'Save something learned while porting a screen (logic source, rule, accepted difference, gotcha, remaining work) into design-specs/notes.json so it need not be found again. Write in English; keep Vietnamese UI text and business wording verbatim in quotes. Regenerates that screen\'s spec.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', description: 'Screen code' },
        kind: { type: 'string', enum: ['logic', 'rules', 'differences', 'gotchas', 'todo'] },
        text: { type: 'string', description: 'One short, concrete sentence (file, function, exact text)' },
      },
      required: ['id', 'kind', 'text'],
    },
    run: ({ id, kind, text: note }) => {
      const s = findScreen(id);
      if (!String(note || '').trim()) throw new Error('text is empty');
      lib.addNote(s.id, kind, String(note).trim());
      invalidate();
      const fresh = findScreen(s.id);
      const out = path.join(lib.SPECS, 'screens', `${s.id}.md`);
      fs.mkdirSync(path.dirname(out), { recursive: true });
      fs.writeFileSync(out, lib.screenMarkdown(fresh, model()));
      return text(`Saved (${kind}) for ${s.id} in ${lib.rel(lib.NOTES)} and updated ${lib.rel(out)}.`);
    },
  },
  {
    name: 'regenerate_specs',
    description: 'Regenerate all of design-specs/ (index, INDEX.md, BLOCKS.md, screens/*.md) from the canvas + code + notes.',
    inputSchema: { type: 'object', properties: {} },
    run: () => {
      invalidate();
      const { execFileSync } = require('child_process');
      const out = execFileSync(process.execPath, [path.join(__dirname, '../scripts/design-specs.cjs')], { encoding: 'utf8' });
      return text(out.trim());
    },
  },
];

// ---------- prompts ----------
function promptsList() {
  const port = {
    name: 'port_screen',
    description: 'Port/rebuild one Pema screen in KMP + Compose from its saved spec (no need to re-read the web/canvas).',
    arguments: [{ name: 'id', description: 'Screen code (A1 … K3)', required: true }],
  };
  return [port, ...model().screens.map((s) => ({ name: s.id, description: `${s.name} · group ${s.group} (${s.source.kind === 'web' ? 'web' : 'Flutter'})` }))];
}

function promptGet(name, args = {}) {
  const s = findScreen(name === 'port_screen' ? args.id : name);
  return {
    description: `${s.id} · ${s.name}`,
    messages: [
      {
        role: 'user',
        content: {
          type: 'text',
          text: `${lib.screenPrompt(s)}\n\nFull spec (read this instead of the web/canvas; if you find something new, save it with the record_note tool):\n\n${lib.screenMarkdown(s, model())}`,
        },
      },
    ],
  };
}

// ---------- resources ----------
function resourcesList() {
  return [
    { uri: 'pema-design://index', name: 'Screen index', mimeType: 'text/markdown' },
    { uri: 'pema-design://blocks', name: 'Canvas block → Compose', mimeType: 'text/markdown' },
    ...model().screens.map((s) => ({ uri: `pema-design://screens/${s.id}`, name: `${s.id} · ${s.name}`, mimeType: 'text/markdown' })),
  ];
}

function resourceRead(uri) {
  if (uri === 'pema-design://index') return lib.indexMarkdown(model());
  if (uri === 'pema-design://blocks') return lib.blocksMarkdown();
  const m = /^pema-design:\/\/screens\/(\w+)$/.exec(uri);
  if (m) return lib.screenMarkdown(findScreen(m[1]), model());
  throw new Error('No resource ' + uri);
}

// ---------- JSON-RPC 2.0 over stdio (newline-delimited, MCP stdio transport) ----------
function send(msg) {
  process.stdout.write(JSON.stringify(msg) + '\n');
}

function handle(req) {
  const { id, method, params = {} } = req;
  const reply = (result) => id !== undefined && send({ jsonrpc: '2.0', id, result });
  const fail = (code, message) => id !== undefined && send({ jsonrpc: '2.0', id, error: { code, message } });
  try {
    switch (method) {
      case 'initialize': {
        const v = SUPPORTED.includes(params.protocolVersion) ? params.protocolVersion : SUPPORTED[0];
        return reply({
          protocolVersion: v,
          capabilities: { tools: {}, prompts: {}, resources: {} },
          serverInfo: SERVER,
          instructions: 'Per-screen specs of the Pema app (canvas Pema App.dc.html → KMP/Compose). Before building/changing a screen: get_screen(id). After learning something new: record_note.',
        });
      }
      case 'notifications/initialized':
      case 'notifications/cancelled':
        return;
      case 'ping':
        return reply({});
      case 'tools/list':
        return reply({ tools: TOOLS.map(({ run, ...t }) => t) });
      case 'tools/call': {
        const tool = TOOLS.find((t) => t.name === params.name);
        if (!tool) return fail(-32602, 'Unknown tool ' + params.name);
        try {
          return reply(tool.run(params.arguments || {}));
        } catch (e) {
          return reply({ isError: true, content: [{ type: 'text', text: e.message }] });
        }
      }
      case 'prompts/list':
        return reply({ prompts: promptsList() });
      case 'prompts/get':
        return reply(promptGet(params.name, params.arguments));
      case 'resources/list':
        return reply({ resources: resourcesList() });
      case 'resources/read':
        return reply({ contents: [{ uri: params.uri, mimeType: 'text/markdown', text: resourceRead(params.uri) }] });
      default:
        return fail(-32601, 'Method not found: ' + method);
    }
  } catch (e) {
    return fail(-32603, e.message);
  }
}

let buffer = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => {
  buffer += chunk;
  let nl;
  while ((nl = buffer.indexOf('\n')) >= 0) {
    const line = buffer.slice(0, nl).trim();
    buffer = buffer.slice(nl + 1);
    if (!line) continue;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      send({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } });
      continue;
    }
    (Array.isArray(msg) ? msg : [msg]).forEach(handle);
  }
});
process.stdin.on('end', () => process.exit(0));
