"""Every test runs with a fresh home folder: the CLI would otherwise create its secret key in the real one."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "agent-home"
    monkeypatch.setattr("agent_app.cli.DEFAULT_HOME", home)
    return home
