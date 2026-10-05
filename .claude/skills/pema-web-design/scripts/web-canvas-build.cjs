#!/usr/bin/env node
// W3a: writes the web canvases from template.html + nodes.html + parts/*.js + tokens.json.
// W10: two outputs from the same base.js, blocks.js and tail.js (owner decision 2026-10-05):
//   "Pema Web.dc.html"            groups WA-WI, the old web only
//   "Pema Web (Next.js).dc.html"  groups WJ, WK, WL, the screens that exist only in the Next.js front end
//
//   node web-canvas-build.cjs            write both canvases (output is deterministic)
//   node web-canvas-build.cjs --check    exit 1 when a committed canvas differs from what the build would write now,
//                                        when a part does not evaluate, when the tokens differ from tokens.json, when the old-web
//                                        canvas holds a WJ/WK/WL frame or the Next.js canvas holds any other group
//   node web-canvas-build.cjs --blocks   write "Pema Web blocks.dc.html", the block gallery (parts/blocks.js, ids WA9xx), instead
//   node web-canvas-build.cjs --file="Pema Web (Next.js).dc.html"   build only this one canvas file
//   node web-canvas-build.cjs --out=<file>   write somewhere else (an agent that must not commit the generated file); needs --file or --blocks when more than one canvas would be built
//
// A group agent edits only its parts/<group>.js, runs this script locally to see the result, and commits the part only.
const fs = require('fs');
const path = require('path');
const lib = require('./lib/web-canvas-lib.cjs');

const args = process.argv.slice(2);
const CHECK = args.includes('--check');
const OUT = (args.find((a) => a.startsWith('--out=')) || '').slice(6);
const FILE = (args.find((a) => a.startsWith('--file=')) || '').slice(7);
const BLOCKS = args.includes('--blocks');

const files = BLOCKS ? [lib.BLOCKS_FILE] : FILE ? [FILE] : Object.keys(lib.OUTPUTS);
if (FILE && !lib.OUTPUTS[FILE]) {
  console.error(`FAILED --file must be one of: ${Object.keys(lib.OUTPUTS).join(' | ')}`);
  process.exit(1);
}
if (OUT && files.length > 1) {
  console.error('FAILED --out needs --file=<canvas file> (or --blocks): more than one canvas would be written');
  process.exit(1);
}

const DCLogic = class {
  constructor() {
    this.props = {};
  }
};

/** Builds one canvas, evaluates it, and returns { text, groups, count, problems }. */
function buildOne(fileName) {
  const blocks = fileName === lib.BLOCKS_FILE;
  const text = lib.buildCanvas({ blocks, file: fileName });
  // the script must evaluate (kinds, depth, ids are validated inside build())
  const m = /<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/.exec(text);
  const groups = new Function('DCLogic', `${m[1]}\nreturn new Component().build();`)(DCLogic);
  const count = groups.reduce((n, g) => n + g.screens.length, 0);
  const problems = [];
  if (!blocks) {
    // the old-web canvas has no WJ/WK/WL frame, the Next.js canvas only those
    const allowed = lib.groupsOfFile(fileName);
    for (const g of groups) {
      if (!allowed.includes(g.code) && g.screens.length) problems.push(`${fileName} holds ${g.screens.length} frame(s) of group ${g.code}, which belongs in the other canvas file`);
    }
    for (const code of allowed) {
      const g = groups.find((x) => x.code === code);
      if (!g) problems.push(`${fileName} has no group ${code}`);
    }
  }
  return { text, groups, count, problems, blocks };
}

try {
  let failed = false;
  for (const fileName of files) {
    const target = OUT ? path.resolve(OUT) : path.join(lib.CANVAS_DIR, fileName);
    const { text, groups, count, problems, blocks } = buildOne(fileName);
    if (CHECK) {
      problems.push(...lib.compareTokens(text));
      const have = fs.existsSync(target) ? lib.lf(fs.readFileSync(target, 'utf8')) : null;
      if (have !== text) problems.push(`${path.relative(lib.ROOT, target)} is stale: run node .claude/skills/pema-web-design/scripts/web-canvas-build.cjs${blocks ? ' --blocks' : ` --file="${fileName}"`}`);
      if (problems.length) {
        problems.forEach((p) => console.error('FAILED ' + p));
        failed = true;
        continue;
      }
      console.log(`${fileName} up to date: ${count} screens in ${groups.length} groups, ${Buffer.byteLength(text)} bytes, tokens equal tokens.json`);
      continue;
    }
    if (problems.length) {
      problems.forEach((p) => console.error('FAILED ' + p));
      failed = true;
      continue;
    }
    fs.writeFileSync(target, text);
    console.log(`wrote ${path.relative(lib.ROOT, target)}: ${count} screens, ${Buffer.byteLength(text)} bytes`);
  }
  // the block gallery is part of a plain --check, like before
  if (CHECK && !BLOCKS && !FILE && !OUT) {
    const gallery = path.join(lib.CANVAS_DIR, lib.BLOCKS_FILE);
    if (fs.existsSync(gallery)) {
      const have = lib.lf(fs.readFileSync(gallery, 'utf8'));
      if (have !== lib.buildCanvas({ blocks: true })) {
        console.error(`FAILED ${path.relative(lib.ROOT, gallery)} is stale: run node .claude/skills/pema-web-design/scripts/web-canvas-build.cjs --blocks`);
        failed = true;
      }
    }
  }
  process.exit(failed ? 1 : 0);
} catch (e) {
  console.error('FAILED ' + (e && e.message ? e.message : e));
  process.exit(1);
}
