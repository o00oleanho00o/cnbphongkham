"""Puts ``pema-agent/`` on ``sys.path`` so the tests of this directory can ``import evals.*``.

The project runs pytest with ``--import-mode=importlib``, which does not do it by itself."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
