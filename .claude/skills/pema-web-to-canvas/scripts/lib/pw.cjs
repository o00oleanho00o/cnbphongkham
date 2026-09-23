// Resolves Playwright without adding it to any package.json:
// PLAYWRIGHT_MODULE env → normal require → npx cache (npx -y playwright@latest --version fills it).
const fs = require('fs');
const path = require('path');
const os = require('os');

function candidates() {
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
  const tries = [process.env.PLAYWRIGHT_MODULE, 'playwright', ...candidates()].filter(Boolean);
  for (const t of tries) {
    try {
      return require(t);
    } catch {}
  }
  throw new Error(
    'Playwright not found. Run `npx -y playwright@latest install chromium` once, ' +
      'or set PLAYWRIGHT_MODULE to a playwright package directory.',
  );
}

module.exports = { loadPlaywright };
