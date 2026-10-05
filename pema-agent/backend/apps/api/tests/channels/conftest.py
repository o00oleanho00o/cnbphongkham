from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.channels.busy_wait_notice import reset_tran_an
from pema.channels.payload_anomaly_watch import reset_anomaly_throttle
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)


@pytest.fixture(autouse=True)
def channel_test_defaults() -> Iterator[None]:
    """Send delay 0 (as the original ``setupTestEnv``), and no throttle memory carried over between tests."""
    install_tuning_provider(StaticTuningProvider({"SEND_DELAY_MIN_MS": 0, "SEND_DELAY_MAX_MS": 0}))
    reset_tran_an()
    reset_anomaly_throttle()
    yield
    reset_tuning_provider()
