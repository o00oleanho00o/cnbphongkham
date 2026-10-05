"""PORT-MAP.md must cover 100% of ``src/`` of the zalo-agent clone and must not lie about finished work.

The clone lives OUTSIDE the repository (``E:\\Desktop\\zalo-agent-ref`` by default, override with
``PEMA_ZALO_REF``). Without it the coverage test is skipped; the structural tests still run.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
PEMA_DIR = API_DIR / "pema"
BACKEND = API_DIR.parents[1]
PORT_MAP = API_DIR.parents[2] / "docs" / "PORT-MAP.md"
REF = Path(os.environ.get("PEMA_ZALO_REF", "E:/Desktop/zalo-agent-ref"))

PACKAGES = {"A", "B1", "B2", "C1", "C2", "D1", "D2", "D3", "D4", "D5", "S", "P", "E", "F", "G"}
ROW = re.compile(
    r"^\| `(?P<src>[^`]+)` \| (?P<lines>[^|]*) \| (?P<target>.+?) \| (?P<owner>[^|]+) \| (?P<note>.*) \|$"
)


def _rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in PORT_MAP.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            rows.append({k: v.strip() for k, v in match.groupdict().items()})
    return rows


def test_port_map_records_clone_path_and_commit() -> None:
    text = PORT_MAP.read_text(encoding="utf-8")
    assert "E:\\Desktop\\zalo-agent-ref" in text
    assert re.search(r"Commit \| `[0-9a-f]{40}`", text)


def test_every_row_has_a_known_owner_or_is_a_no_port() -> None:
    bad: list[str] = []
    for row in _rows():
        owners = [o.strip() for o in row["owner"].split(",")]
        if row["target"] == "no port":
            if owners != ["-"] or not row["note"]:
                bad.append(f"{row['src']}: a no-port row needs owner '-' and a reason")
        elif not set(owners) <= PACKAGES:
            bad.append(f"{row['src']}: unknown package {owners}")
    assert bad == []


def test_src_python_targets_stay_inside_the_agreed_layout() -> None:
    bad: list[str] = []
    for row in _rows():
        target = row["target"].strip("`")
        if row["src"].startswith("src/") and target != "no port":
            first = re.split(r" \+ | \(", target)[0]
            if first.startswith("pema/"):
                top = first.split("/")[1]
                if not (PEMA_DIR / top).exists() and not (PEMA_DIR / top).with_suffix(".py").exists():
                    bad.append(f"{row['src']} -> {first}: pema/{top} does not exist")
    assert bad == []


def test_rows_marked_as_done_by_package_a_really_exist() -> None:
    missing: list[str] = []
    for row in _rows():
        if row["owner"] != "A":
            continue
        for token in re.findall(r"(?:pema|tests|packages)/[\w/.\-]+\.py", row["target"]):
            path = API_DIR / token if token.startswith(("pema/", "tests/")) else BACKEND / token
            if not path.exists():
                missing.append(f"{row['src']} -> {token}")
    assert missing == []


@pytest.mark.skipif(not (REF / "src").exists(), reason="zalo-agent reference clone not found")
def test_port_map_covers_every_file_of_src_exactly_once() -> None:
    expected = {
        f"src/{p.relative_to(REF / 'src').as_posix()}" for p in (REF / "src").rglob("*") if p.is_file()
    }
    listed = [row["src"] for row in _rows() if row["src"].startswith("src/")]
    assert len(listed) == len(set(listed)), "a file is listed twice"
    assert expected - set(listed) == set(), "files of src/ missing from PORT-MAP"
    assert set(listed) - expected == set(), "PORT-MAP lists files that are not in the clone"


@pytest.mark.skipif(not (REF / "web").exists(), reason="zalo-agent reference clone not found")
def test_port_map_covers_every_dashboard_file() -> None:
    expected = {
        p.relative_to(REF).as_posix()
        for p in (REF / "web").rglob("*")
        if p.is_file() and "node_modules" not in p.parts
    }
    listed = {row["src"] for row in _rows() if row["src"].startswith("web/")}
    assert expected - listed == set()
