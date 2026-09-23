import { readdirSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const canvasDir = resolve(here, process.env.DC_CANVAS_DIR ?? '../Pema App redesign canvas');

const VIRTUAL_ID = 'virtual:dc-files';
const RESOLVED_ID = `\0${VIRTUAL_ID}`;

const listDocs = () =>
  readdirSync(canvasDir)
    .filter((name) => name.endsWith('.dc.html'))
    .sort();

const canvasPath = (file: string) => {
  const rel = relative(canvasDir, file);
  return rel.startsWith('..') || isAbsolute(rel) ? null : rel.split('\\').join('/');
};

// Serves the canvas folder as-is and tells the viewer which document changed,
// so it can hot-swap the page instead of reloading and losing the camera.
function dcCanvas(): Plugin {
  return {
    name: 'dc-canvas',
    resolveId: (id) => (id === VIRTUAL_ID ? RESOLVED_ID : undefined),
    load: (id) => (id === RESOLVED_ID ? `export default ${JSON.stringify(listDocs())};` : undefined),
    configureServer(server) {
      server.watcher.add(canvasDir);
      const onDocsListChanged = (file: string) => {
        const rel = canvasPath(file);
        if (!rel?.endsWith('.dc.html')) return;
        const mod = server.moduleGraph.getModuleById(RESOLVED_ID);
        if (mod) server.moduleGraph.invalidateModule(mod);
        server.ws.send({ type: 'full-reload' });
      };
      server.watcher.on('add', onDocsListChanged);
      server.watcher.on('unlink', onDocsListChanged);
    },
    handleHotUpdate({ file, server }) {
      const rel = canvasPath(file);
      if (!rel) return;
      server.ws.send({ type: 'custom', event: 'dc:changed', data: { file: rel } });
      return [];
    },
  };
}

export default defineConfig({
  plugins: [react(), dcCanvas()],
  publicDir: canvasDir,
  server: { port: 4180 },
  preview: { port: 4181 },
});
