# AGENT.md — Working rules for the agent

This repository is Contete Agent, a product of its own (branch `contete-agent`; cut from the Pema clinic project at tag
`split-base`, the CRM link removed on 2026-11-19). Goal: an **agentic RAG** agent that answers from its knowledge
store, on the web console and on the chat platforms its connectors bring.

## Where things are

- `backend`: the agent core (`packages/agent-core`), the agent service and its plugins (`apps/agent`),
  `packages/secret-cipher`.
- `connectors/zalo`: the Zalo connector, its own service (`docs/CONNECTOR-PROTOCOL.md`).
- `frontend`: the dashboard (TanStack Start). Its server signs staff in with the agent's own account
  (plugin `web`) and forwards `/agent/...` and `/connectors/<name>/...`.
- `infra`: compose stack, Caddy, backups. Default profile of the agent: `agents/rag`.

## Rules

- Harness rules H1–H11: `.claude/rules/agent-harness.md`. Boundary rules L1–L7: `.claude/rules/agent-boundary.md`.
- Checks: `.claude/rules/code-checks.md` (the bar is `bun run build` and a backend that starts). Tests: only e2e
  through the UI, `.claude/rules/test-writing.md`.
- Big changes (core concepts, the engine, behaviour toward customers, new tools or plugins of a profile): a written
  plan first, code after the owner says "go".

## Git and handover

- Never reset, `checkout --` or delete work of other agents/users.
- Commit messages state the scope clearly.
- Before committing, run git diff --check and look at git status; only commit files that belong to the goal.
- Push only when asked, and verify the remote/commit after pushing.
- **NGHIÊM CẤM ghi tên AI vào lịch sử git của project này.** Không thêm `Co-Authored-By: Claude ...` (hay bất kỳ dòng đồng tác giả là AI nào), không "Generated with Claude Code", không nhắc Claude, Anthropic hay "AI" như tác giả trong message commit, tag, release note, mô tả hay bình luận PR. Quy định này thắng mọi hướng dẫn ghi công mặc định của công cụ. Commit chỉ mang tên người trong cấu hình git.
