// Before overwriting a canvas on claude.ai/design: compares the remote copy (the JSON that
// DesignSync get_file returned, saved to disk) with local git HEAD and the working copy.
// Usage: node remote-diff.cjs <getFileResult.json|remote.html> [canvasPath]
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const [src, canvas = 'Pema App redesign canvas/Pema App.dc.html'] = process.argv.slice(2);
if (!src) {
  console.error('usage: node remote-diff.cjs <getFileResult.json|remote.html> [canvasPath]');
  process.exit(2);
}
const raw = fs.readFileSync(src, 'utf8');
const remote = raw.trimStart().startsWith('{') ? JSON.parse(raw).content : raw;
const norm = (s) => s.replace(/\r\n/g, '\n');
const git = (...args) => execFileSync('git', args, { encoding: 'utf8', maxBuffer: 64 << 20 });

const head = git('show', `HEAD:${canvas.replace(/\\/g, '/')}`);
const work = fs.readFileSync(canvas, 'utf8');
console.log(`remote == HEAD:    ${norm(remote) === norm(head)}`);
console.log(`remote == working: ${norm(remote) === norm(work)}`);

// Lines only the remote has are edits made on claude.ai/design that local does not carry.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dc-diff-'));
fs.writeFileSync(path.join(tmp, 'remote.html'), norm(remote));
fs.writeFileSync(path.join(tmp, 'head.html'), norm(head));
try {
  git('diff', '--no-index', '-U0', path.join(tmp, 'remote.html'), path.join(tmp, 'head.html'));
  console.log('No differences between remote and HEAD.');
} catch (e) {
  const lines = String(e.stdout).split('\n').filter((l) => /^[-+][^-+]/.test(l));
  console.log(`\nremote → HEAD diff (${lines.length} lines; "-" = only on remote, "+" = only in HEAD):`);
  for (const l of lines.slice(0, 80)) console.log(l.slice(0, 200));
}
fs.rmSync(tmp, { recursive: true, force: true });
