"""Guard: no logger call in pema/care passes a reserved LogRecord attribute in `extra=`.

logging raises KeyError("Attempt to overwrite 'created' in LogRecord") only when the record is actually
built, i.e. when the level is enabled. A care-only run can hide that, a full run (where another test turns
the level up) does not. This scan makes it independent of the log level.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pema.care

RESERVED = set(logging.LogRecord("n", 20, "f", 1, "m", (), None).__dict__) | {"message", "asctime"}
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}


def _reserved_extra_keys(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in LOG_METHODS:
            continue
        for kw in node.keywords:
            if kw.arg != "extra" or not isinstance(kw.value, ast.Dict):
                continue
            for key in kw.value.keys:
                if isinstance(key, ast.Constant) and key.value in RESERVED:
                    found.append(f"{path.name}:{node.lineno} {key.value}")
    return found


def test_no_logger_call_in_care_uses_a_reserved_logrecord_key() -> None:
    root = Path(next(iter(pema.care.__path__)))
    offenders = [hit for p in sorted(root.rglob("*.py")) for hit in _reserved_extra_keys(p)]
    assert offenders == []
