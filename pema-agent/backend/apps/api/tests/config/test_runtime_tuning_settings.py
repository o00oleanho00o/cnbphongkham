# Contract tests for the cross-package tuning API. D1 ports runtime-tuning-settings.test.ts on top of this.
from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    UnknownTuningKeyError,
    bot_time_zone,
    get_tuning,
    get_tuning_bool,
    get_tuning_int,
    install_tuning_provider,
    reset_tuning_provider,
    tuning_default,
)
from pema.config.tuning_specs import TUNING_SPECS


@pytest.fixture(autouse=True)
def _clean_provider() -> Iterator[None]:
    reset_tuning_provider()
    yield
    reset_tuning_provider()


def test_all_72_parameters_are_present_with_original_defaults() -> None:
    assert len(TUNING_SPECS) == 72
    assert get_tuning("HISTORY_CONTEXT_LIMIT") == 20
    assert get_tuning("SCHEDULER_MAX_PROACTIVE_PER_DAY") == 10
    assert get_tuning("ZALO_MAX_MESSAGE_CHARS") == 2000
    assert get_tuning("LLM_REASONING_EFFORT") == "medium"
    assert bot_time_zone() == "Asia/Ho_Chi_Minh"
    assert get_tuning_bool("SCHEDULER_ENABLED") is True


def test_defaults_respect_their_own_bounds() -> None:
    for key, spec in TUNING_SPECS.items():
        value = tuning_default(key)
        if spec.kind == "number":
            assert isinstance(value, int | float)
            assert spec.minimum is not None
            assert spec.maximum is not None
            assert spec.minimum <= value <= spec.maximum, key
        if spec.kind == "enum":
            assert value in spec.options, key


def test_override_wins_over_default() -> None:
    install_tuning_provider(StaticTuningProvider({"HISTORY_CONTEXT_LIMIT": 40, "AGENT_TRACE_ENABLED": False}))
    assert get_tuning("HISTORY_CONTEXT_LIMIT") == 40
    assert get_tuning_int("HISTORY_CONTEXT_LIMIT") == 40
    assert get_tuning_bool("AGENT_TRACE_ENABLED") is False


def test_environment_sits_between_override_and_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KB_TOP_K", "9")
    assert get_tuning("KB_TOP_K") == 9
    assert tuning_default("KB_TOP_K") == 9
    install_tuning_provider(StaticTuningProvider({"KB_TOP_K": 3}))
    assert get_tuning("KB_TOP_K") == 3
    assert tuning_default("KB_TOP_K") == 9


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("HISTORY_CONTEXT_LIMIT", "not-a-number"),
        ("HISTORY_CONTEXT_LIMIT", 100000),
        ("HISTORY_CONTEXT_LIMIT", 0),
        ("LLM_REASONING_EFFORT", "extreme"),
        ("BOT_TIMEZONE", "Khong/Ton_Tai"),
        ("KB_TOP_K", "nan"),
    ],
)
def test_corrupt_stored_value_is_ignored_not_fatal(key: str, bad: str | int) -> None:
    default = tuning_default(key)
    install_tuning_provider(StaticTuningProvider({key: bad}))
    assert get_tuning(key) == default


def test_valid_override_of_time_zone_and_enum() -> None:
    install_tuning_provider(
        StaticTuningProvider({"BOT_TIMEZONE": "Europe/Paris", "LLM_REASONING_EFFORT": "high"})
    )
    assert bot_time_zone() == "Europe/Paris"
    assert get_tuning("LLM_REASONING_EFFORT") == "high"


def test_unknown_key_raises_a_named_error() -> None:
    with pytest.raises(UnknownTuningKeyError):
        get_tuning("NOT_A_PARAMETER")


def test_wrong_accessor_type_is_a_programming_error() -> None:
    with pytest.raises(TypeError):
        get_tuning_int("SCHEDULER_ENABLED")
    with pytest.raises(TypeError):
        get_tuning_bool("KB_TOP_K")
