from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)


@pytest.fixture(autouse=True)
def zero_send_delay() -> Iterator[None]:
    """The original test environment (``setupTestEnv``) sets the send delay to 0."""
    install_tuning_provider(StaticTuningProvider({"SEND_DELAY_MIN_MS": 0, "SEND_DELAY_MAX_MS": 0}))
    yield
    reset_tuning_provider()
