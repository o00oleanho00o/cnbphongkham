# frontend

The Contete Agent dashboard: one TanStack Start app (file routes, run by bun, TypeScript, Tailwind v4, Vietnamese UI).
Its pages are the agent console (`/admin/agent/...`): the web plugin's pages and the pages each plugin and connector
ships. It is UI only; every rule is the agent's.

Its server (`src/lib/server`) signs staff in with the agent's own account (plugin `web`), keeps that login in the
httpOnly cookie `contete_session`, and forwards `/agent/...` to the agent (`CONTETE_AGENT_INTERNAL_URL`) and
`/connectors/<name>/...` to the connectors (`CONTETE_CONNECTOR_URLS`).

## Run

```
bun install
bun run dev:mock        # mock agent and connector on :4010 plus vite dev on :3000 (no other service needed)
bun run dev             # against a real agent (CONTETE_AGENT_INTERNAL_URL)
bun run build && bun run start      # the build is the Nitro server in .output/, run by bun
bun run e2e             # Playwright on a running stack (e2e/playwright.config.ts); the only tests of this repo
```

`src/lib/api/schema.d.ts`, `FEATURE-INVENTORY.md` and `visual-ref/` are left from the clinic web this app was cut from.
