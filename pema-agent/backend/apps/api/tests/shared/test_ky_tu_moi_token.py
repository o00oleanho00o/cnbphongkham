# ported from: src/shared/ky-tu-moi-token.test.ts
from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from pema.shared.ky_tu_moi_token import KY_TU_MOI_TOKEN, uoc_token_tu_ky_tu

PEMA_ROOT = Path(__file__).resolve().parents[2] / "pema"


def test_uoc_token_tu_ky_tu_converts_by_the_constant_and_rounds_up() -> None:
    """quy đổi theo đúng KY_TU_MOI_TOKEN và làm tròn LÊN

    Rounded up, not down: this estimate is used to BLOCK, so under-estimating lets a config past the cap.
    """
    assert uoc_token_tu_ky_tu(2500) == 1000
    assert uoc_token_tu_ky_tu(1) == 1
    assert uoc_token_tu_ky_tu(0) == 0


@pytest.mark.parametrize("n", [500, 1200, 8000, 15_000, 20_000, 100_000])
def test_uoc_token_tu_ky_tu_matches_the_direct_division(n: int) -> None:
    """khớp phép chia trực tiếp bằng hằng số"""
    assert uoc_token_tu_ky_tu(n) == math.ceil(n / KY_TU_MOI_TOKEN)


@pytest.mark.parametrize(
    ("relative", "pattern"),
    [
        ("config/runtime_tuning_settings.py", r"_CHARS['\"]\)\s*/\s*\d"),
        ("agent/token_estimate.py", r"len\([^)]*\)\s*/\s*\d"),
    ],
)
def test_there_is_only_one_chars_to_token_constant(relative: str, pattern: str) -> None:
    """không nơi nào tự chia cho một số ký tự/token khác

    The paid-for bug: a cross rule wrote ``/ 4`` (the English figure) while the real estimator ran at 2.5.
    Both guarded files exist now (``agent/token_estimate.py`` landed with D1), so no case is skipped.
    """
    path = PEMA_ROOT / relative
    found = re.search(pattern, path.read_text(encoding="utf-8"))
    assert found is None, f'{relative} divides a length by a literal ("{found and found.group(0)}")'
