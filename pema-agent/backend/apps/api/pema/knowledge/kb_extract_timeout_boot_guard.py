# ported from: src/config/kb-extract-timeout-boot-guard.test.ts (guard at the end of src/config/env.ts)
"""Boot guard for ``KB_EXTRACT_TIMEOUT_MS`` in the environment.

Why it exists (original): the schema floor of this variable was lowered (100 ms) ONLY so a test can reach a
REAL overrun through the environment; without a guard of its own that low floor becomes the only fence for a
REAL ``.env``: whoever types "600" meaning "600 seconds" (or "1000") still boots quietly, and then EVERY
document that overruns is blamed as a "poisoned document" while the real root cause is one line of ``.env``.

Forced deviation: in this port ``get_tuning`` (package A) already refuses a value outside ``[min, max]`` and
falls back to the default, which is silent - exactly the failure the guard exists to prevent. This function
makes the worker process REFUSE TO START instead. It is called by ``pema.workers.kb_ingest_worker`` before the
loop starts. ``PEMA_ENVIRONMENT=test`` keeps the original seam: a value below the floor is allowed there
(tests normally bypass the tuning with ``CaiDatIngest`` instead, see ``tests/knowledge``).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Final

from pema.config.tuning_specs import TUNING_SPECS

CHIA_KHOA: Final = "KB_EXTRACT_TIMEOUT_MS"
SAN_TEST_MS: Final = 100
"""The floor kept for ``PEMA_ENVIRONMENT=test`` (the original ``min(100)`` of the environment schema)."""


class CauHinhKhongHopLeError(ValueError):
    """The environment holds a value the worker must not boot with. The message names the variable."""


def kiem_tra_kb_extract_timeout(environ: Mapping[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    raw = env.get(CHIA_KHOA)
    if raw is None or raw.strip() == "":
        return  # unset: the default of the spec (60000 ms) - the most common case

    spec = TUNING_SPECS[CHIA_KHOA]
    san = int(spec.minimum) if spec.minimum is not None else 0
    tran = int(spec.maximum) if spec.maximum is not None else 600_000
    if env.get("PEMA_ENVIRONMENT", "dev") == "test":
        san = SAN_TEST_MS
    try:
        gia_tri = int(raw)
    except ValueError:
        raise CauHinhKhongHopLeError(
            f"{CHIA_KHOA} phải là số nguyên (mili giây), nhận được {raw!r}"
        ) from None
    if gia_tri < san or gia_tri > tran:
        raise CauHinhKhongHopLeError(
            f"{CHIA_KHOA}={gia_tri} nằm ngoài khoảng cho phép {san}-{tran} mili giây "
            "(nhầm giây thành mili giây?). Sửa dòng này trong .env rồi khởi động lại."
        )
