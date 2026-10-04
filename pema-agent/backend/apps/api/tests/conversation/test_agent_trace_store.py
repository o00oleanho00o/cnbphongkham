# ported from: src/agent/agent-trace-store.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

``traceLuotHong`` (``failed-turn-trace.ts``) lives in ``pema_contracts.turn_errors`` as ``failed_turn_step``.
The test "dòng ghi trước khi có cột attempt đọc ra 1" of the original covered an ``ALTER TABLE`` upgrade of an
older SQLite file; the column is created with a default in Postgres, so it is checked as "a step inserted without
``attempt`` reads back 1". Steps now have a foreign key to their turn: the "orphan step" cases of the original are
guaranteed by the database (tested in ``test_wipe_thread_context``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider
from pema.conversation.agent_trace_store import AgentTraceStore
from pema.conversation.pg_testing import ClinicEnv
from pema.conversation.thread_store import ThreadStoreImpl
from pema.conversation.usage_store import UsageStoreImpl
from pema_contracts.agent_turn import StepTrace, TokenUsage
from pema_contracts.turn_errors import (
    GuardBlockReason,
    PromptLeakReason,
    ProviderErrorReason,
    failed_turn_step,
)

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _tuning() -> None:  # pyright: ignore[reportUnusedFunction]
    install_tuning_provider(StaticTuningProvider({"AGENT_TRACE_RETENTION_DAYS": 7}))


def _step(n: int, **extra: object) -> StepTrace:
    base: dict[str, object] = {
        "step_number": n,
        "attempt": 1,
        "text": f"noi gi do {n}",
        "reasoning": "",
        "tool_calls": [],
        "tool_results": [],
        "tool_errors": [],
        "finish_reason": "stop",
        "warnings": [],
        "input_tokens": 100 * n,
        "output_tokens": 10 * n,
    }
    return StepTrace.model_validate(base | extra)


async def _record_turn(usage: UsageStoreImpl, env: ClinicEnv, thread_id: str = "t-1", steps: int = 2) -> int:
    """Một lượt trọn vẹn: mở lượt rồi chốt usage - đúng đường production đi."""
    turn_id = await usage.open_agent_turn(env.clinic_id, "acc-1", thread_id)
    await usage.finish_agent_turn(
        env.clinic_id,
        turn_id,
        TokenUsage(input_tokens=1000, output_tokens=100, total_tokens=1100, steps=steps),
    )
    return turn_id


async def test_open_agent_turn_returns_an_id_to_link_the_trace_positive_and_increasing(
    env: ClinicEnv,
) -> None:
    """openAgentTurn trả về id để nối trace: id là số dương và tăng dần"""
    usage = UsageStoreImpl(env.db)
    first = await _record_turn(usage, env)
    second = await _record_turn(usage, env)
    assert first > 0
    assert second > first, "lượt sau phải có id lớn hơn"


async def test_agent_trace_store_save_then_read_back_in_step_order(env: ClinicEnv) -> None:
    """lưu rồi đọc lại đúng thứ tự step"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, turn_id, [_step(1), _step(2), _step(3)])

    trace = await store.get_turn_trace(env.clinic_id, turn_id)
    assert [s.step_number for s in trace] == [1, 2, 3]
    assert trace[0].text == "noi gi do 1"


async def test_agent_trace_store_keeps_tool_calls_warnings_and_reasoning_through_save_and_read(
    env: ClinicEnv,
) -> None:
    """giữ nguyên toolCalls, warnings, reasoning qua vòng lưu/đọc"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env)
    await store.save_turn_trace(
        env.clinic_id,
        turn_id,
        [
            _step(
                1,
                reasoning="Ta cần cộng 2 và 3",
                tool_calls=[{"name": "create_image", "input": '{"mode":"ve_moi"}'}],
                tool_results=[{"name": "create_image", "output": "Đã vẽ và GỬI ảnh"}],
                warnings=["unsupported-setting - size"],
            )
        ],
    )

    step = (await store.get_turn_trace(env.clinic_id, turn_id))[0]
    assert step.reasoning == "Ta cần cộng 2 và 3"
    assert step.tool_calls == [{"name": "create_image", "input": '{"mode":"ve_moi"}'}]
    assert step.tool_results == [{"name": "create_image", "output": "Đã vẽ và GỬI ảnh"}]
    assert step.warnings == ["unsupported-setting - size"]


async def test_agent_trace_store_turn_without_steps_writes_nothing_and_does_not_raise(env: ClinicEnv) -> None:
    """lượt không có step nào thì không ghi gì, không throw"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, turn_id, [])
    assert await store.get_turn_trace(env.clinic_id, turn_id) == []


async def test_agent_trace_store_reading_the_trace_of_a_missing_turn_returns_an_empty_list(
    env: ClinicEnv,
) -> None:
    """đọc trace của lượt không tồn tại trả mảng rỗng"""
    assert await AgentTraceStore(env.db).get_turn_trace(env.clinic_id, 999999) == []


async def test_agent_trace_store_lists_recent_turns_of_a_thread_with_step_counts_for_the_dashboard(
    env: ClinicEnv,
) -> None:
    """liệt kê các lượt gần đây của thread kèm số step - cho dashboard"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    first = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, first, [_step(1), _step(2)])
    second = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, second, [_step(1)])

    turns = await store.get_recent_turns(env.clinic_id, "acc-1", "t-1", 10)
    assert len(turns) == 2
    assert turns[0].id == second, "mới nhất đứng đầu"
    assert turns[0].step_count == 1
    assert turns[1].step_count == 2


async def test_agent_trace_store_recent_turns_cursor_returns_only_older_turns(env: ClinicEnv) -> None:
    """(thêm) nút 'Xem thêm': before_id chỉ lấy lượt cũ hơn id đã cho"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    ids = [await _record_turn(usage, env) for _ in range(3)]
    older = await store.get_recent_turns(env.clinic_id, "acc-1", "t-1", 10, before_id=ids[2])
    assert [t.id for t in older] == [ids[1], ids[0]]


async def test_agent_trace_store_other_threads_do_not_mix(env: ClinicEnv) -> None:
    """thread khác không lẫn vào nhau"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    first = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, first, [_step(1)])
    other = await _record_turn(usage, env, "t-KHAC", 1)
    await store.save_turn_trace(env.clinic_id, other, [_step(1)])

    assert len(await store.get_recent_turns(env.clinic_id, "acc-1", "t-1", 10)) == 1


# ----------------------------------------------------------------- liệt kê lượt toàn hệ thống


async def test_all_threads_list_merges_every_thread_newest_first_with_display_names(env: ClinicEnv) -> None:
    """gộp lượt của MỌI thread, mới nhất đứng đầu, kèm tên hiển thị"""
    await ThreadStoreImpl(env.db).record_thread_activity(
        env.clinic_id,
        account_id="acc-1",
        thread_id="t-1",
        thread_type=0,
        display_name="Anh Hải",
        sender_name="Hải",
    )
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    first = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, first, [_step(1)])
    second = await _record_turn(usage, env, "t-KHAC", 1)
    await store.save_turn_trace(env.clinic_id, second, [_step(1), _step(2)])

    turns = await store.get_recent_turns_all_threads(env.clinic_id, 10)

    assert len(turns) == 2
    assert turns[0].id == second, "mới nhất đứng đầu"
    assert turns[0].thread_id == "t-KHAC"
    assert turns[0].step_count == 2
    assert turns[1].display_name == "Anh Hải", "thread có tên thì hiện tên"


async def test_all_threads_list_unnamed_thread_falls_back_to_the_thread_id(env: ClinicEnv) -> None:
    """thread chưa có tên thì rơi về threadId, không để trống"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, turn_id, [_step(1)])
    assert (await store.get_recent_turns_all_threads(env.clinic_id, 10))[0].display_name == "t-1"


async def test_all_threads_list_only_lists_turns_that_have_a_trace(env: ClinicEnv) -> None:
    """CHỈ liệt kê lượt CÓ trace - lượt không trace lên danh sách là bấm vào rỗng"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    await _record_turn(usage, env)  # không lưu trace
    traced = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, traced, [_step(1)])

    turns = await store.get_recent_turns_all_threads(env.clinic_id, 10)
    assert len(turns) == 1
    assert turns[0].id == traced


async def test_all_threads_list_cursor_returns_only_older_turns(env: ClinicEnv) -> None:
    """(thêm) con trỏ before_id cũng áp cho danh sách toàn hệ thống"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    ids: list[int] = []
    for _ in range(3):
        turn_id = await _record_turn(usage, env)
        await store.save_turn_trace(env.clinic_id, turn_id, [_step(1)])
        ids.append(turn_id)
    older = await store.get_recent_turns_all_threads(env.clinic_id, 10, before_id=ids[2])
    assert [t.id for t in older] == [ids[1], ids[0]]


# ----------------------------------------------------------------- dọn trace cũ


async def test_prune_old_traces_removes_expired_and_keeps_current(env: ClinicEnv) -> None:
    """xóa trace quá hạn, GIỮ trace còn hạn"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    old = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, old, [_step(1)])
    new = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, new, [_step(1)])

    # Lùi ngày tường minh thay vì chờ thời gian trôi (bài học test chập chờn)
    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    await env.execute(
        "UPDATE agent.usage_steps SET created_at = :at WHERE turn_id = :t", at=ten_days_ago, t=old
    )

    removed = await store.prune_old_traces(env.clinic_id, 7)

    assert removed == 1
    assert await store.get_turn_trace(env.clinic_id, old) == [], "trace 10 ngày tuổi phải bị dọn"
    assert len(await store.get_turn_trace(env.clinic_id, new)) == 1, "trace còn hạn phải được giữ"


async def test_prune_old_traces_default_retention_comes_from_the_tuning_key(env: ClinicEnv) -> None:
    """(thêm) không truyền số ngày thì dùng AGENT_TRACE_RETENTION_DAYS (ở đây 7)"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env)
    await store.save_turn_trace(env.clinic_id, turn_id, [_step(1)])
    await env.execute(
        "UPDATE agent.usage_steps SET created_at = :at WHERE turn_id = :t",
        at=datetime.now(UTC) - timedelta(days=8),
        t=turn_id,
    )
    assert await store.prune_old_traces(env.clinic_id) == 1


# ----------------------------------------------------------------- lần chạy lại và lỗi tool


async def test_save_turn_trace_retry_keeps_attempt_and_orders_attempt_one_before_two(env: ClinicEnv) -> None:
    """giữ đúng attempt và xếp lần 1 trước lần 2, không trộn theo step_number"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env, "t-retry", 2)
    # Lượt có retry: mỗi lần chạy đánh số step lại từ 1
    await store.save_turn_trace(
        env.clinic_id, turn_id, [_step(1, attempt=1), _step(2, attempt=1), _step(1, attempt=2)]
    )

    trace = await store.get_turn_trace(env.clinic_id, turn_id)
    assert [(s.attempt, s.step_number) for s in trace] == [(1, 1), (1, 2), (2, 1)], (
        "xếp theo step_number đơn thuần sẽ ra 1,1,2 - đọc như model lặp"
    )


async def test_save_turn_trace_step_inserted_without_attempt_reads_back_as_one(env: ClinicEnv) -> None:
    """dòng ghi trước khi có cột attempt đọc ra 1, không phải undefined"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env, "t-cu", 1)
    await env.execute(
        "INSERT INTO agent.usage_steps (clinic_id, turn_id, step_number, text) VALUES (:c, :t, 1, 'cu')",
        c=env.clinic_id,
        t=turn_id,
    )
    assert (await store.get_turn_trace(env.clinic_id, turn_id))[0].attempt == 1


async def test_save_turn_trace_tool_errors_round_trip(env: ClinicEnv) -> None:
    """ghi và đọc lại được lỗi tool"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env, "thread-loi", 1)
    await store.save_turn_trace(
        env.clinic_id,
        turn_id,
        [_step(1, tool_errors=[{"name": "create_image", "error": "prompt vượt 4000 ký tự"}])],
    )
    trace = await store.get_turn_trace(env.clinic_id, turn_id)
    assert trace[0].tool_errors == [{"name": "create_image", "error": "prompt vượt 4000 ký tự"}]


async def test_save_turn_trace_row_without_tool_errors_reads_back_as_an_empty_list(env: ClinicEnv) -> None:
    """dòng cũ không có lỗi tool đọc ra mảng rỗng, không phải undefined"""
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env, "thread-cu", 1)
    await store.save_turn_trace(env.clinic_id, turn_id, [_step(1)])
    assert (await store.get_turn_trace(env.clinic_id, turn_id))[0].tool_errors == []


async def test_saving_a_trace_for_a_turn_that_does_not_exist_is_refused(env: ClinicEnv) -> None:
    """(thêm) khóa ngoại: trace của lượt không tồn tại là mồ côi nên bị từ chối"""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await AgentTraceStore(env.db).save_turn_trace(env.clinic_id, 424242, [_step(1)])


# ----------------------------------------------------------------- lượt hỏng trước khi chạy step nào


async def test_failed_turn_with_a_synthetic_trace_is_listed_and_its_reason_can_be_read(
    env: ClinicEnv,
) -> None:
    """có trace tổng hợp thì lên danh sách VÀ bấm vào đọc được lý do"""
    # "Has a step" is deliberate: the way for a turn that dies at the first call not to vanish is to GIVE it a
    # trace, not to loosen the filter (that only turns "vanishes" into "opens empty").
    usage, store = UsageStoreImpl(env.db), AgentTraceStore(env.db)
    turn_id = await _record_turn(usage, env)
    await store.save_turn_trace(
        env.clinic_id,
        turn_id,
        [failed_turn_step(ProviderErrorReason(error_kind="cau_hinh", message="Chưa cấu hình model"))],
    )

    turns = await store.get_recent_turns_all_threads(env.clinic_id, 10)
    assert any(t.id == turn_id for t in turns), "lượt hỏng phải lên danh sách"

    steps = await store.get_turn_trace(env.clinic_id, turn_id)
    assert len(steps) == 1
    assert steps[0].finish_reason == "error:cau_hinh"
    assert "Chưa cấu hình model" in steps[0].text


async def test_the_three_kinds_of_failed_turn_are_told_apart_by_finish_reason() -> None:
    """ba loại lượt hỏng phân biệt được bằng finishReason"""
    # Trước đây cả ba chỉ để lại một dòng log; trên UI nhìn y hệt nhau (hoặc y hệt một lượt thành công, với ca chặn
    # rò prompt).
    codes = [
        failed_turn_step(ProviderErrorReason(error_kind="auth", message="x")).finish_reason,
        failed_turn_step(GuardBlockReason(code="loi-giong-het", message="y")).finish_reason,
        failed_turn_step(PromptLeakReason()).finish_reason,
    ]
    assert codes == ["error:auth", "blocked:loi-giong-het", "blocked:prompt-leak"]
    assert len(set(codes)) == 3
