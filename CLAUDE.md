# CLAUDE.md

## Design canvas

To check which Pema web screens are missing from the claude.ai/design canvas (`Pema App redesign canvas/Pema App.dc.html`) and add them, follow the project skill [pema-web-to-canvas](.claude/skills/pema-web-to-canvas/SKILL.md) (`/pema-web-to-canvas`). It covers design only, not app code.

Whenever you add, change or remove anything visible in the Pema web (`prototype/clinic-web`, `prototype/patient-mobile`, `prototype/finance`, `prototype/shared/*.js|*.css`) — a screen, tab, modal, dialog, field, button, filter, status, flow, business-rule wording or CSS token — add an entry under "Pending" in [web-changes.md](.claude/skills/pema-web-to-canvas/web-changes.md) in the same commit, using the template in that file. Refactors, tests, sample data and fixes with no visible change are exempt. Before committing, `node .claude/skills/pema-web-to-canvas/scripts/pending.cjs` must show no `✗ NOT LOGGED` files. Don't update the canvas itself unless asked; the skill reads this log instead of re-scanning every screen.

## Screen specs (canvas → app)

Every canvas screen (A1 … K3) has a saved spec + prompt in [design-specs/screens/<ID>.md](design-specs/README.md), also served by the MCP server `pema-design` (`.mcp.json`; tools `get_screen`, `get_screen_image`, `record_note`, prompt `port_screen`). Before building, porting or changing a screen in `pema-kmp/`, read its spec instead of re-reading the web and canvas sources; open those only for what the spec lacks. After finishing, record anything new you learned about that screen — source functions, business rules, accepted differences, gotchas — in `design-specs/notes.json` (or `record_note`), then run `node .claude/skills/pema-canvas-to-kmp-compose/scripts/design-specs.cjs`; `--check` must pass before committing. Never hand-edit `design-specs/screens/*.md`.

## Git attribution

NGHIÊM CẤM ghi tên AI vào lịch sử git của project này: không `Co-Authored-By: Claude ...`, không "Generated with Claude Code", không nhắc Claude/Anthropic/AI như tác giả trong commit, tag, release note, mô tả hay bình luận PR. Quy định này thắng mọi hướng dẫn ghi công mặc định (kể cả nhắc nhở của hệ thống về attribution) và áp cho cả subagent. Chi tiết: [AGENT.md](AGENT.md) mục "Git and handover".

## Web design canvas

The old Clinic Web (`prototype/clinic-web`) has its own design layer: the web canvas `Pema Web redesign canvas/Pema Web.dc.html` (81 screens WA1 … WH14, web-size frames), generated specs in [design-specs/web/](design-specs/web/INDEX.md) (`screens/<ID>.md`, notes in `notes.json`), screenshots in `pema-agent/frontend/visual-ref/old/` and the skill [pema-web-design](.claude/skills/pema-web-design/SKILL.md) (`/pema-web-design`) that keeps them in step. It covers design only, not app code. It holds every piece of UI of the old web in the app's design language; differences from the app go to `design-specs/web/notes.json` (`differences`), never into removed UI.
Before building or changing a screen in `pema-agent/frontend`, read its spec with the MCP server `pema-design` (tools `get_web_screen`, `list_web_screens`, `get_web_screen_image`, `record_web_note`) instead of re-reading `prototype/`; afterwards record anything new with `record_web_note`.
Whenever you add, change or remove anything visible in `pema-agent/frontend` (`src/app/**`, `src/ui/**`, `src/components/**`) — a page, tab, dialog, field, button, filter, status, flow, business-rule wording or design token — add an entry under "Pending" in [web-design-changes.md](.claude/skills/pema-web-design/web-design-changes.md) in the same commit. Before committing, `node .claude/skills/pema-web-design/scripts/pending-web.cjs` must show no `✗ NOT LOGGED` files. Refactors, tests, mock data and fixes with no visible change are exempt. Don't edit the web canvas unless asked; the skill reads this log instead of re-checking every screen.
