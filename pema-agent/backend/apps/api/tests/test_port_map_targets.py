"""Package G cross-check of PORT-MAP.md against the code that really exists (no zalo-agent source).

``test_port_map.py`` (package A) proves that the table LISTS every file of ``src/`` and ``web/``. This module
proves the other half: that what the table PROMISES exists.

* ``test_every_src_file_has_an_existing_python_target``: for every file of ``src/`` of the reference clone
  (``E:\\Desktop\\zalo-agent-ref``, read only) that is not a ``no port`` row, every path of the ``Python
  target`` column must exist on disk (``pema/...``, ``tests/...``, ``packages/...``, ``frontend/...``), or the
  source must be claimed by a ``# ported from:`` header of a file that does exist (the port was placed under a
  different name than the row says; the row is stale, the work is not missing). What is truly missing must be
  written in ``KNOWN_MISSING_TARGETS`` with its owner: the test pins that dict exactly, so a gap can neither
  grow unnoticed nor linger after it was fixed;
* ``test_every_ported_from_header_points_at_an_existing_file``: every Python file that opens with ``# ported
  from: src/<path>.ts`` names files that exist in the clone (a typo or a renamed upstream file is a lie about
  provenance, and THIRD_PARTY_NOTICES depends on that provenance being true);
* ``test_every_ported_from_header_has_a_port_map_row``: the source a header names has a real row (not
  ``no port``). ``KNOWN_HEADER_WITHOUT_ROW`` pins the rows that are stale.

Without the clone every test here is skipped (same rule as ``test_port_map.py``); set ``PEMA_ZALO_REF`` to
point at another location.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
AGENT_ROOT = API_DIR.parents[2]
BACKEND = API_DIR.parents[1]
PORT_MAP = AGENT_ROOT / "docs" / "PORT-MAP.md"
REF = Path(os.environ.get("PEMA_ZALO_REF", "E:/Desktop/zalo-agent-ref"))

ROW = re.compile(
    r"^\| `(?P<src>[^`]+)` \| (?P<lines>[^|]*) \| (?P<target>.+?) \| (?P<owner>[^|]+) \| (?P<note>.*) \|$"
)
PATH_TOKEN = re.compile(r"(?:^|[\s`+])((?:pema|tests|packages|frontend|evals|infra|backend|docs)/\S*)")
SOURCE_NAME = re.compile(r"[\w\-./]+\.(?:tsx|ts|jsx|js|mjs|cjs|json|css|html)")
HEADER_LINES = 8

KNOWN_MISSING_TARGETS: dict[str, str] = {}
"""``<row source>`` -> ``package that owns the missing target``. Empty: every target the table promises exists
(the last one, the route test of ``POST /auth/password``, was written in the final integration round)."""

KNOWN_HEADER_WITHOUT_ROW: frozenset[str] = frozenset()
"""Sources a ``# ported from:`` header names while PORT-MAP.md says ``no port``. Empty: the two
``xoa-han-session`` rows now point at ``pema/conversation/xoa_han_session.py``."""

# Assigned in the same module as the helpers below so ``skipif`` can see the clone.
pytestmark = pytest.mark.skipif(not (REF / "src").exists(), reason="zalo-agent reference clone not found")


def _rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in PORT_MAP.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            rows.append({k: v.strip() for k, v in match.groupdict().items()})
    return rows


def _resolve(token: str) -> Path:
    token = token.rstrip(".,;:")
    root = token.split("/", 1)[0]
    if root in ("pema", "tests"):
        return API_DIR / token
    if root == "packages":
        return BACKEND / token
    return AGENT_ROOT / token


def _targets(row: dict[str, str]) -> list[str]:
    return [t.rstrip(".,;:") for t in PATH_TOKEN.findall(row["target"].replace("`", " "))]


def _python_sources() -> list[Path]:
    files: list[Path] = []
    for base in (API_DIR / "pema", API_DIR / "tests", BACKEND / "packages", AGENT_ROOT / "evals"):
        files.extend(p for p in base.rglob("*.py") if ".venv" not in p.parts and "__pycache__" not in p.parts)
    return files


def _declared_sources(path: Path) -> list[str]:
    """Upstream files named by the ``# ported from:`` header (it may continue on the next comment lines and
    may name several files; a bare file name lives in the folder of the first full path)."""
    with path.open(encoding="utf-8") as handle:
        lines = [handle.readline() for _ in range(HEADER_LINES)]
    collected: list[str] = []
    capturing = False
    for line in lines:
        text = line.strip()
        if text.startswith("# ported from:"):
            capturing = True
            text = text.removeprefix("# ported from:")
        elif capturing and text.startswith("#"):
            text = text.removeprefix("#")
        else:
            capturing = False
            continue
        collected.extend(SOURCE_NAME.findall(text))
    declared: list[str] = []
    folder = ""
    for name in collected:
        if name.startswith(("src/", "web/")):
            folder = name.rsplit("/", 1)[0] + "/"
            declared.append(name)
        elif folder:
            declared.append(folder + name)
    return declared


def _claimed_sources() -> set[str]:
    claimed: set[str] = set()
    for path in _python_sources():
        claimed.update(_declared_sources(path))
    return claimed


def test_every_src_file_has_an_existing_python_target() -> None:
    src_files = {
        f"src/{p.relative_to(REF / 'src').as_posix()}" for p in (REF / "src").rglob("*") if p.is_file()
    }
    by_src = {row["src"]: row for row in _rows()}
    assert src_files - set(by_src) == set(), "files of src/ with no row in PORT-MAP.md"

    claimed = _claimed_sources()
    missing: dict[str, str] = {}
    for src in sorted(src_files):
        row = by_src[src]
        if row["target"] == "no port":
            continue
        targets = _targets(row)
        if not targets:
            # ``alembic 0002 (agent.kb_document ...)``: a table of a migration, no file to look for
            assert "alembic" in row["target"], f"{src}: the target column names no path: {row['target']!r}"
            continue
        if any(not _resolve(t).exists() for t in targets) and src not in claimed:
            missing[src] = row["owner"]
    assert missing == KNOWN_MISSING_TARGETS, (
        "targets that PORT-MAP promises but do not exist (src -> owner), differences with the pinned list: "
        + ", ".join(
            f"{s} -> {o}" for s, o in sorted(set(missing.items()) ^ set(KNOWN_MISSING_TARGETS.items()))
        )
    )


def test_every_ported_from_header_points_at_an_existing_file() -> None:
    dangling: list[str] = []
    for path in _python_sources():
        for declared in _declared_sources(path):
            if not (REF / declared).is_file():
                dangling.append(f"{path.relative_to(AGENT_ROOT).as_posix()} -> {declared}")
    assert dangling == []


def test_every_ported_from_header_has_a_port_map_row() -> None:
    real_rows = {row["src"] for row in _rows() if row["target"] != "no port"}
    stray: set[str] = set()
    for path in _python_sources():
        stray.update(d for d in _declared_sources(path) if d not in real_rows)
    assert stray == set(KNOWN_HEADER_WITHOUT_ROW), (
        "a header names a source that PORT-MAP.md has no real row for: " + ", ".join(sorted(stray))
    )
