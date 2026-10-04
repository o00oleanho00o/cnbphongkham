# ported from: src/scheduler/delivery-attempt-store.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from pema.scheduler.delivery_attempt_store import MAX_DELIVERY_ATTEMPTS
from pema.scheduler.testing_env import Env

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]


async def test_increment_delivery_attempts_new_job_starts_at_0_first_increment_gives_1(
    make_env: EnvMaker,
) -> None:
    """job mới tạo: delivery_attempts ngầm định 0, tăng lần đầu ra 1"""
    env = make_env()
    job = await env.make_job(thread_id="t-tang-lan-dau")
    assert await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id) == 1


async def test_increment_delivery_attempts_several_increments_accumulate(make_env: EnvMaker) -> None:
    """tăng nhiều lần cộng dồn đúng"""
    env = make_env()
    job = await env.make_job(thread_id="t-tang-nhieu-lan")
    assert [await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id) for _ in range(3)] == [
        1,
        2,
        3,
    ]


async def test_increment_delivery_attempts_unknown_job_is_a_no_op_returning_0(make_env: EnvMaker) -> None:
    """job không tồn tại: UPDATE no-op, trả về 0 (không ném lỗi)"""
    env = make_env()
    assert await env.deps.attempts.increment_delivery_attempts(env.clinic_id, "khong-ton-tai") == 0


async def test_increment_delivery_attempts_concurrent_failures_get_distinct_values(
    make_env: EnvMaker,
) -> None:
    """(Postgres) 10 lần thất bại đồng thời nhận 10 giá trị khác nhau - UPDATE ... RETURNING, không đọc-rồi-ghi"""
    env = make_env()
    job = await env.make_job(thread_id="t-tang-dong-thoi")
    values = await asyncio.gather(
        *(env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id) for _ in range(10))
    )
    assert sorted(values) == list(range(1, 11))


async def test_reset_delivery_attempts_back_to_0_after_a_few_increments(make_env: EnvMaker) -> None:
    """đưa về 0 sau khi đã tăng vài lần"""
    env = make_env()
    job = await env.make_job(thread_id="t-reset")
    await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id)
    await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id)
    await env.deps.attempts.reset_delivery_attempts(env.clinic_id, job.id)
    assert await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id) == 1, (
        "sau reset, tăng lần kế phải ra lại 1"
    )


def test_max_delivery_attempts_is_3_the_decision_try_at_most_3_times() -> None:
    """là 3 - đúng quyết định 'thử tối đa 3 lần' của thiết kế"""
    assert MAX_DELIVERY_ATTEMPTS == 3
