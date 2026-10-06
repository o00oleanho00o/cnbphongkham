// Resolves Playwright without adding it to any package.json. Same contract as the pema-web-to-canvas loader.
// Order: PLAYWRIGHT_MODULE env -> <repo>/pema-agent/frontend/node_modules/playwright -> normal require -> npx cache.
const fs = require('fs');
const path = require('path');
const os = require('os');

const REPO = path.resolve(__dirname, '..', '..', '..', '..', '..');

function npxCandidates() {
  const roots = [
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'npm-cache', '_npx'),
    path.join(os.homedir(), '.npm', '_npx'),
  ].filter(Boolean);
  const found = [];
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    for (const dir of fs.readdirSync(root)) {
      const mod = path.join(root, dir, 'node_modules', 'playwright');
      if (fs.existsSync(path.join(mod, 'package.json'))) found.push(mod);
    }
  }
  return found;
}

function loadPlaywright() {
  const tries = [
    process.env.PLAYWRIGHT_MODULE,
    path.join(REPO, 'pema-agent', 'frontend', 'node_modules', 'playwright'),
    'playwright',
    ...npxCandidates(),
  ].filter(Boolean);
  for (const t of tries) {
    try {
      return require(t);
    } catch {
      // try the next candidate
    }
  }
  throw new Error(
    'Playwright not found. Set PLAYWRIGHT_MODULE to a playwright package directory, ' +
      'or run `npx -y playwright@latest install chromium` once.',
  );
}

module.exports = { loadPlaywright, REPO };
