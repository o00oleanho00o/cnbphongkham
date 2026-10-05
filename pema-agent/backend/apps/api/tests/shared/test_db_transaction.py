# ported from: src/shared/db-transaction.test.ts
"""``in_transaction`` against a fake session that records the order of calls (no database needed)."""

from __future__ import annotations

import pytest

from pema.shared.db_transaction import in_transaction


class FakeSession:
    def __init__(self, rollback_error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._rollback_error = rollback_error

    async def begin(self) -> object:
        self.calls.append("BEGIN")
        return self

    async def commit(self) -> None:
        self.calls.append("COMMIT")

    async def rollback(self) -> None:
        self.calls.append("ROLLBACK")
        if self._rollback_error is not None:
            raise self._rollback_error


async def test_success_path_begin_then_commit_returns_the_value_of_work() -> None:
    """đường thành công: BEGIN rồi COMMIT, trả về đúng giá trị của viec()"""
    session = FakeSession()

    async def work() -> int:
        return 42

    assert await in_transaction(session, work) == 42
    assert session.calls == ["BEGIN", "COMMIT"]


async def test_work_raises_rolls_back_never_commits_and_reraises_the_original_error() -> None:
    """viec() ném lỗi: gọi ROLLBACK, KHÔNG gọi COMMIT, ném lại đúng lỗi gốc"""
    session = FakeSession()
    original = ValueError("lỗi từ viec()")

    async def work() -> None:
        raise original

    with pytest.raises(ValueError, match="lỗi từ viec") as info:
        await in_transaction(session, work)
    assert info.value is original
    assert session.calls == ["BEGIN", "ROLLBACK"], "COMMIT must not run when work fails"


async def test_work_and_rollback_both_raise_the_original_error_still_wins() -> None:
    """viec() ném VÀ chính ROLLBACK cũng ném: lỗi lọt ra ngoài vẫn là lỗi GỐC, không phải lỗi rollback"""
    session = FakeSession(rollback_error=RuntimeError("lỗi khi rollback"))
    original = ValueError("lỗi từ viec()")

    async def work() -> None:
        raise original

    with pytest.raises(ValueError, match="lỗi từ viec") as info:
        await in_transaction(session, work)
    assert info.value is original, "the rollback error must be swallowed, not override the original"
