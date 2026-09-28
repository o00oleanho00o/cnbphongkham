// Writes the per-screen conversion specs to design-specs/ (index.json, INDEX.md, screens/<ID>.md).
//   node design-specs.cjs            → regenerate
//   node design-specs.cjs --check    → exit 1 if design-specs/ is out of date (CI / before commit)
//   node design-specs.cjs --show=I2  → print one screen spec to stdout
const fs = require('fs');
const path = require('path');
const lib = require('./specs-lib.cjs');

const args = process.argv.slice(2);
const check = args.includes('--check');
const show = args.find((a) => a.startsWith('--show='))?.slice(7);

const model = lib.buildModel();
if (show) {
  const s = model.screens.find((x) => x.id.toLowerCase() === show.toLowerCase());
  if (!s) {
    console.error('Không có màn ' + show);
    process.exit(1);
  }
  process.stdout.write(lib.screenMarkdown(s, model));
  process.exit(0);
}

const files = new Map();
files.set(path.join(lib.SPECS, 'index.json'), JSON.stringify(model, null, 2) + '\n');
files.set(path.join(lib.SPECS, 'INDEX.md'), lib.indexMarkdown(model));
files.set(path.join(lib.SPECS, 'BLOCKS.md'), lib.blocksMarkdown());
for (const s of model.screens) files.set(path.join(lib.SPECS, 'screens', `${s.id}.md`), lib.screenMarkdown(s, model));

const screensDir = path.join(lib.SPECS, 'screens');
const stale = fs.existsSync(screensDir)
  ? fs.readdirSync(screensDir).filter((f) => f.endsWith('.md') && !files.has(path.join(screensDir, f)))
  : [];

if (check) {
  const changed = [...files].filter(([p, text]) => !fs.existsSync(p) || fs.readFileSync(p, 'utf8') !== text).map(([p]) => lib.rel(p));
  if (changed.length || stale.length) {
    console.error(`design-specs lỗi thời (${changed.length + stale.length} file): ${[...changed, ...stale].slice(0, 8).join(', ')} … → chạy node design-specs.cjs`);
    process.exit(1);
  }
  console.log(`design-specs khớp (${model.screens.length} màn)`);
  process.exit(0);
}

fs.mkdirSync(screensDir, { recursive: true });
let written = 0;
for (const [p, text] of files) {
  if (fs.existsSync(p) && fs.readFileSync(p, 'utf8') === text) continue;
  fs.writeFileSync(p, text);
  written++;
}
for (const f of stale) fs.unlinkSync(path.join(screensDir, f));
const ported = model.screens.filter((s) => s.status === 'ported').length;
console.log(`design-specs: ${model.screens.length} màn (${ported} đã port), ${written} file cập nhật → ${lib.rel(lib.SPECS)}`);
