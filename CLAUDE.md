# CLAUDE.md

## Design canvas

To check which Pema web screens are missing from the claude.ai/design canvas (`Pema App redesign canvas/Pema App.dc.html`) and add them, follow the project skill [pema-web-to-canvas](.claude/skills/pema-web-to-canvas/SKILL.md) (`/pema-web-to-canvas`). It covers design only, not `.dart` code.

Whenever you add, change or remove anything visible in the Pema web (`prototype/clinic-web`, `prototype/patient-mobile`, `prototype/finance`, `prototype/shared/*.js|*.css`) — a screen, tab, modal, dialog, field, button, filter, status, flow, business-rule wording or CSS token — add an entry under "Chờ chuyển" in [web-changes.md](.claude/skills/pema-web-to-canvas/web-changes.md) in the same commit, using the template in that file. Refactors, tests, sample data and fixes with no visible change are exempt. Before committing, `node .claude/skills/pema-web-to-canvas/scripts/pending.cjs` must show no `✗ CHƯA GHI` files. Don't update the canvas itself unless asked; the skill reads this log instead of re-scanning every screen.

## Flutter rules

Official rules from [flutter/agent-plugins/rules](https://github.com/flutter/agent-plugins/tree/main/rules) (plugin `dart-flutter@dart-flutter`). The Flutter app lives in `flutter-template/`.

### Proactive Flutter Hot Reload Rule

Whenever you edit or modify any `.dart` file under `flutter-template/lib/`:

1. **When to Skip**:
   - **Files Outside `lib/`**: Only trigger hot reload or hot restart for edits under `lib/`. Do not trigger when modifying files in other directories (e.g., `test/**`, `integration_test/**`, `benchmark/**`, `test_driver/**` or `example/**`).
   - **Comments & Documentation**: Do not trigger hot reload or hot restart when changes only affect comments, docstrings, or whitespace.

2. **Discover & Connect**:
   - Discover active running application instances using the `dtd` MCP Tool (or `list_running_apps` / `vm_service`) from the Dart MCP server.

3. **Trigger Hot Reload / Hot Restart**:
   - Execute the `hot_reload` MCP tool immediately after making changes to UI widgets (including `build` methods of stateful widgets) or simple methods.
   - Execute the `hot_restart` MCP tool if fundamental logic, state initialization (e.g., `initState`), global/static state, or `main()` was modified.
