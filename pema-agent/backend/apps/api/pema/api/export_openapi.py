"""Write the OpenAPI document: ``python -m pema.api.export_openapi [path]``.

Default target is ``apps/api/openapi.json`` (committed; the FE generates its types from it).
Output is deterministic (sorted keys, trailing newline) so diffs show real contract changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pema.bootstrap import create_app

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def render_openapi() -> str:
    schema = create_app().openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else DEFAULT_PATH
    target.write_text(render_openapi(), encoding="utf-8", newline="\n")
    sys.stdout.write(f"wrote {target}\n")
    return 0


def main_cli() -> int:
    return main(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
