# ported from: src/shared/logger-turn-fields.test.ts
"""Regression for a bug that reached a real turn in zalo-agent: each log line must carry ONLY its own
fields, never those accumulated from earlier lines (pino's mixin merge once wrote into the shared
context object). Here the turn context is copied per record. Plus the clinic additions: PII keys are
redacted and errors are serialised safely."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from pema.shared.logger import REDACTED, configure_logging, create_logger
from pema.shared.turn_log_context import TurnLogContext, current_turn_log_context, run_in_turn_log_context


@pytest.fixture
def log_file(tmp_path: Path) -> Iterator[Path]:
    configure_logging("ERROR", file_enabled=True, log_dir=tmp_path, keep_days=2)
    yield tmp_path / "bot.log"
    root = logging.getLogger("pema")
    for handler in list(root.handlers):
        handler.flush()
        handler.close()
        root.removeHandler(handler)


def _lines(path: Path) -> list[dict[str, object]]:
    for handler in logging.getLogger("pema").handlers:
        handler.flush()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def test_each_line_carries_only_its_own_fields_not_the_previous_ones(log_file: Path) -> None:
    """mỗi dòng chỉ mang trường của CHÍNH nó, không tích lũy của dòng trước"""
    log = create_logger("fake-tool")

    async def turn() -> None:
        log.error("dòng một", result_count=3, tool_results=["nội dung trang web"])
        await asyncio.sleep(0.005)
        log.error("dòng hai", url="https://vi.du")

    await run_in_turn_log_context(TurnLogContext("acc-1", "t-1", 99), turn)

    lines = _lines(log_file)
    two = next(line for line in lines if line["msg"] == "dòng hai")
    assert two["turn_id"] == 99, "the turn fields are still there"
    assert two["url"] == "https://vi.du"
    assert "result_count" not in two, "field of the previous line must not bleed over"
    assert "tool_results" not in two


async def test_the_turn_context_object_is_not_mutated_by_logging(log_file: Path) -> None:
    """object ngữ cảnh trong AsyncLocalStorage không bị pino ghi đè"""
    context = TurnLogContext("acc-2", "t-2", 100)

    async def turn() -> None:
        create_logger("x").error("có ghi gì đó", rac_rac="abc")
        await asyncio.sleep(0.005)
        assert current_turn_log_context() == context, "context must stay intact"

    await run_in_turn_log_context(context, turn)


def test_pii_keys_are_redacted_and_ids_are_kept(log_file: Path) -> None:
    create_logger("channel").error(
        "inbound", text="chảy máu nhiều", sender_name="Nguyễn Văn A", phone="0000000000", thread_id="t-9"
    )
    line = _lines(log_file)[-1]
    assert line["text"] == REDACTED
    assert line["sender_name"] == REDACTED
    assert line["phone"] == REDACTED
    assert line["thread_id"] == "t-9"
    raw = log_file.read_text(encoding="utf-8")
    assert "chảy máu" not in raw
    assert "Nguyễn" not in raw


def test_err_is_serialised_safely(log_file: Path) -> None:
    class LeakyError(Exception):
        def __init__(self) -> None:
            super().__init__("boom")
            self.request_body_values = {"messages": ["SECRET CONVERSATION"]}

    create_logger("llm").error("call failed", err=LeakyError())
    raw = log_file.read_text(encoding="utf-8")
    assert "SECRET CONVERSATION" not in raw
    assert "boom" in raw
