# Report — step <O?> <name>

**Worktree/branch:** <branch>  
**Recipe:** `recipes/O/<file>.md`  
**Status:** done | partial | blocked

## Built
- <models, actions, routers, migrations, FE routes, design ids — 3–8 lines>

## Tests and lint run (real results)
- BE: full `uv run pytest` → <N passed / M skipped / K failed; name any failure other than the 3 known care clock tests>;
  ruff, ruff format --check, pyright, lint-imports → <result>; `alembic heads` → <one head, its name>
- FE (O6): vitest (≥ count at branch start), lint, check:types, build, `pnpm inventory`, `pnpm visual`, `pending-web.cjs` → <result>
- Design (O5): `web-inventory.cjs --check`, `web-specs.cjs --check`, `web-canvas.cjs check --file "Pema Web (Next.js).dc.html" --complete --viewport=all --frames` → <result>
- Security: credential-boundary test (name), PII-free notification test (name), internal notifier never customer-facing (name)

## Assumptions
- <defaults from PLAN-AI01-O §7 you relied on; fakes used>

## Open items
- <owner inputs; things only M7 or package F can finish; cross-package changes you did not make>
