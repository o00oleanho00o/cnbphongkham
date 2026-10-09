# Running tests — run what the change touches, not the whole suite

Applies to every `pytest` run in this repo (mostly `pema-agent/backend`). The full suite takes a long time.

- By default run only the tests that cover the code you changed:
  - the test file of each changed module (e.g. `agentcore/prompt/builder.py` → `packages/agent-core/tests/test_prompt.py`);
  - tests that import or call a changed function or class (search the tests for its name);
  - the tests you added or edited.
  Select by file, node id (`path::test_name`) or `-k`, e.g. `uv run pytest packages/agent-core/tests/test_prompt.py -q`.
- When those targeted tests pass (roughly a fifth of the suite), the step counts as done. Say in the report which
  tests ran and that the full suite did not.
- Run the full suite only when the user asks, before a push or a PR, or when the change touches something every
  test depends on: `conftest.py`, `pyproject.toml` or dependencies, shared fixtures, migrations, or a core type used
  everywhere (e.g. `agentcore.messages`, the session store port).
- After a failure, re-run only the failing tests (`--lf`) until they pass, then the targeted set once more.
- Tests marked `db` need `PEMA_TEST_DATABASE_URL`; run them only when the change touches database code.
- Scope `ruff` and `pyright` to the changed paths as well.
