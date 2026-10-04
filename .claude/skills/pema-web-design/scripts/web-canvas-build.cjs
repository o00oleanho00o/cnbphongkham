#!/usr/bin/env node
// W3a: writes "Pema Web redesign canvas/Pema Web.dc.html" from template.html + nodes.html + parts/*.js + tokens.json.
//
//   node web-canvas-build.cjs            write the canvas (output is deterministic)
//   node web-canvas-build.cjs --check    exit 1 when the committed canvas differs from what the build would write now,
//                                        when a part does not evaluate, or when the tokens differ from tokens.json
//   node web-canvas-build.cjs --blocks   write "Pema Web blocks.dc.html", the block gallery (parts/blocks.js, ids WA9xx), instead
//   node web-canvas-build.cjs --out=<file>   write somewhere else (an agent that must not commit the generated file)
//
// A group agent edits only its parts/<group>.js, runs this script locally to see the result, and commits the part only.
const fs = require('fs');
const path = require('path');
const lib = require('./lib/web-canvas-lib.cjs');

const args = process.argv.slice(2);
const CHECK = args.includes('--check');
const OUT = (args.find((a) => a.startsWith('--out=')) || '').slice(6);
const BLOCKS = args.includes('--blocks');
const target = OUT ? path.resolve(OUT) : path.join(lib.CANVAS_DIR, BLOCKS ? lib.BLOCKS_FILE : lib.CANVAS_FILE);

let text;
try {
  text = lib.buildCanvas({ blocks: BLOCKS });
  // the script must evaluate (kinds, depth, ids are validated inside build())
  const m = /<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/.exec(text);
  const DCLogic = class {
    constructor() {
      this.props = {};
    }
  };
  const groups = new Function('DCLogic', `${m[1]}\nreturn new Component().build();`)(DCLogic);
  const count = groups.reduce((n, g) => n + g.screens.length, 0);
  if (CHECK) {
    const problems = lib.compareTokens(text);
    const stale = (file, want, cmd) => {
      const have = fs.existsSync(file) ? lib.lf(fs.readFileSync(file, 'utf8')) : null;
      if (have !== want) problems.push(`${path.relative(lib.ROOT, file)} is stale: run node .claude/skills/pema-web-design/scripts/web-canvas-build.cjs${cmd}`);
    };
    stale(target, text, BLOCKS ? ' --blocks' : '');
    const gallery = path.join(lib.CANVAS_DIR, lib.BLOCKS_FILE);
    if (!BLOCKS && !OUT && fs.existsSync(gallery)) stale(gallery, lib.buildCanvas({ blocks: true }), ' --blocks');
    if (problems.length) {
      problems.forEach((p) => console.error('FAILED ' + p));
      process.exit(1);
    }
    console.log(`web canvas up to date: ${count} screens in ${groups.length} groups, ${Buffer.byteLength(text)} bytes, tokens equal tokens.json`);
    process.exit(0);
  }
  fs.writeFileSync(target, text);
  console.log(`wrote ${path.relative(lib.ROOT, target)}: ${count} screens, ${Buffer.byteLength(text)} bytes`);
} catch (e) {
  console.error('FAILED ' + (e && e.message ? e.message : e));
  process.exit(1);
}
