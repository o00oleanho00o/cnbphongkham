# Report — step <O?> <name>

**Worktree/branch:** <branch>  
**Recipe:** `recipes/O/<file>.md`  
**Status:** done | partial | blocked

## Built
- <models, actions, routers, migrations, FE routes — 3–8 lines>

## Tests and lint run (real results)
- BE: `uv run pytest apps/api/tests/ops/<...>` → <N passed, M failed>; ruff / pyright / import-linter → <result>
- FE (O5): vitest ≥ baseline, lint, tsc, build, `pnpm inventory`, `pnpm visual` → <result>
- Security checks: credentials never serialized (test name); PII-free notifications (test name)

## Assumptions
- <Protocols created because another package was missing; provider credentials mocked>

## Open items
- <owner inputs: group id, internal account, FCM/APNs; race conditions found; cross-package changes>
