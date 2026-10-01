# ported from: src/conversation/wipe-thread-context.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Xóa ngữ cảnh là thao tác KHÔNG HOÀN TÁC ĐƯỢC. Hai kiểu sai đều tệ theo hướng ngược nhau:

  - Sót một bảng: người dùng tưởng đã sạch, bot vẫn nhắc chuyện cũ (for a clinic: a retention failure).
  - Xóa quá tay: mất dữ liệu của thread khác, của account khác, hoặc mất lịch hẹn - thứ người dùng không hề định bỏ.

Nên mỗi test dựng SẴN dữ liệu của một thread thứ hai và một account thứ hai, rồi khẳng định chúng còn nguyên.
Media files live on a temporary local volume (``tmp_path``) instead of ``dataDir/media``.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from pema.conversation.agent_trace_store import AgentTraceStore
from pema.conversation.history_store import HistoryStoreImpl
from pema.conversation.image_description_store import ImageDescriptionStoreImpl
from pema.conversation.media_store import MediaStore
from pema.conversation.memory_store import MemoryStoreImpl
from pema.conversation.pg_testing import ClinicEnv
from pema.conversation.thread_store import ThreadStoreImpl
from pema.conversation.usage_store import UsageStoreImpl
from pema.conversation.wipe_thread_context import ThreadContextWiper, WipeOptions
from pema_contracts.agent_turn import StepTrace, TokenUsage
from pema_contracts.conversation import StoredMessage

pytestmark = pytest.mark.db

ACC = "acc-1"
ACC_KHAC = "acc-2"
TH = "thread-1"
TH_KHAC = "thread-2"


class Rig:
    def __init__(self, env: ClinicEnv, media_root: Path) -> None:
        self.env = env
        self.history = HistoryStoreImpl(env.db)
        self.threads = ThreadStoreImpl(env.db)
        self.memories = MemoryStoreImpl(env.db)
        self.usage = UsageStoreImpl(env.db)
        self.traces = AgentTraceStore(env.db)
        self.image_desc = ImageDescriptionStoreImpl(env.db)
        self.media = MediaStore(media_root)
        self.wiper = ThreadContextWiper(env.db, self.media, self.image_desc)
        self.media_root = media_root

    @property
    def clinic_id(self) -> UUID:
        return self.env.clinic_id

    async def seed_thread(self, account_id: str, thread_id: str) -> None:
        """Dựng một thread có đủ mọi loại dữ liệu, để phép xóa có thứ thật để xóa."""
        await self.threads.record_thread_activity(
            self.clinic_id,
            account_id=account_id,
            thread_id=thread_id,
            thread_type=0,
            display_name=f"Tên {thread_id}",
            sender_name="Người dùng",
        )
        await self.history.append_message(
            self.clinic_id, account_id, thread_id, StoredMessage(role="user", content="tin của người dùng")
        )
        await self.history.append_message(
            self.clinic_id, account_id, thread_id, StoredMessage(role="assistant", content="bot trả lời")
        )
        await self.threads.set_thread_summary(self.clinic_id, account_id, thread_id, "tóm tắt cũ", 1)
        await self.memories.save_memory_fact(
            self.clinic_id,
            account_id=account_id,
            subject_id="u1",
            content=f"fact học ở {thread_id}",
            learned_in_thread_id=thread_id,
            learned_in_group=False,
        )
        turn_id = await self.usage.open_agent_turn(self.clinic_id, account_id, thread_id)
        await self.usage.finish_agent_turn(
            self.clinic_id, turn_id, TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15, steps=1)
        )

    async def message_count(self, account_id: str, thread_id: str) -> int:
        return len(await self.history.get_recent_messages(self.clinic_id, account_id, thread_id, 100))

    async def seed_image(self, account_id: str, thread_id: str, name: str) -> str:
        rel = "/".join(["media", account_id, thread_id, name])
        absolute = self.media_root / str(self.clinic_id) / rel
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(bytes([0xFF, 0xD8]))
        await self.image_desc.save_image_description(self.clinic_id, rel, "mô tả ảnh", "model-test")
        return rel

    def image_exists(self, rel: str) -> bool:
        return (self.media_root / str(self.clinic_id) / rel).exists()


@pytest.fixture
async def rig(env: ClinicEnv, tmp_path: Path) -> Rig:
    rig = Rig(env, tmp_path / "media-root")
    await rig.seed_thread(ACC, TH)
    await rig.seed_thread(ACC, TH_KHAC)
    await rig.seed_thread(ACC_KHAC, TH)
    return rig


async def _turn_count(rig: Rig, account_id: str, thread_id: str) -> int:
    return int(
        await rig.env.scalar(
            "SELECT COUNT(*) FROM agent.usage WHERE account_id = :a AND thread_id = :t",
            a=account_id,
            t=thread_id,
        )
    )


# ----------------------------------------------------------------- xóa đúng thread


async def test_wipe_thread_context_messages_summary_and_trace_of_that_thread_disappear(rig: Rig) -> None:
    """xoaNguCanhThread - xóa đúng thread: tin nhắn, tóm tắt và trace của thread đó biến mất"""
    result = await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)

    assert await rig.message_count(ACC, TH) == 0, "tin nhắn phải sạch"
    summary = await rig.threads.get_thread_summary(rig.clinic_id, ACC, TH)
    assert summary.summary == "", "tóm tắt phải sạch"
    assert summary.covers_to_message_id == 0, "mốc đã gộp phải về 0"
    assert result.messages == 2


async def test_wipe_thread_context_keeps_the_token_rows_and_only_deletes_the_trace_content(rig: Rig) -> None:
    """xoaNguCanhThread - xóa đúng thread: GIỮ dòng đếm token, chỉ xóa NỘI DUNG trace"""
    # Bản đầu xóa cả ``usage``, và đó là bảng nguồn DUY NHẤT của thống kê token: trang Tổng quan báo hôm nay dùng 0
    # token trong khi bot chạy ~30 lượt. Lịch sử chi tiêu không phải nội dung hội thoại.
    before = await _turn_count(rig, ACC, TH)
    assert before > 0, "phải có lượt để đếm thì phép đo mới có nghĩa"

    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)

    assert await _turn_count(rig, ACC, TH) == before, "xóa usage là thổi bay thống kê token của cả ngày"


async def test_wipe_thread_context_does_not_touch_another_thread_of_the_same_account(rig: Rig) -> None:
    """xoaNguCanhThread - xóa đúng thread: KHÔNG đụng thread khác cùng account"""
    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)
    assert await rig.message_count(ACC, TH_KHAC) == 2, "thread khác phải còn nguyên tin"
    assert (await rig.threads.get_thread_summary(rig.clinic_id, ACC, TH_KHAC)).summary == "tóm tắt cũ"


async def test_wipe_thread_context_does_not_touch_the_same_thread_id_in_another_account(rig: Rig) -> None:
    """xoaNguCanhThread - xóa đúng thread: KHÔNG đụng thread trùng tên ở account khác"""
    # Bẫy thật: ``thread_id`` của Zalo chỉ duy nhất TRONG một account. Quên điều kiện account_id là xóa lây sang
    # nick khác mà không ai thấy.
    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)
    assert await rig.message_count(ACC_KHAC, TH) == 2, "account khác phải còn nguyên"


async def test_wipe_thread_context_keeps_the_thread_row_name_and_bot_switch(rig: Rig) -> None:
    """xoaNguCanhThread - xóa đúng thread: giữ lại dòng threads: tên hiển thị và công tắc bot còn nguyên"""
    await rig.threads.set_bot_enabled(rig.clinic_id, ACC, TH, False)
    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)

    assert await rig.threads.has_display_name(rig.clinic_id, ACC, TH) is True, (
        "đây là reset chứ không phải xóa session"
    )
    assert await rig.threads.is_bot_enabled(rig.clinic_id, ACC, TH) is False, "công tắc bot phải giữ nguyên"


async def test_wipe_thread_context_resets_message_count_of_the_thread_row(rig: Rig) -> None:
    """(thêm) đặt lại message_count vì lịch sử đã trống - để nguyên thì trang Sessions hiện '465 tin' cho thread rỗng"""
    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)
    rows = await rig.threads.list_threads(rig.clinic_id, account_id=ACC, query=TH)
    assert next(r for r in rows if r.thread_id == TH).message_count == 0


async def test_wipe_thread_context_deletes_the_per_thread_proactive_counter_but_not_a_per_patient_one(
    rig: Rig,
) -> None:
    """(thêm) bộ đếm tin chủ động của thread bị xóa (scope 'account:thread'); bộ đếm theo bệnh nhân thì giữ"""
    for scope_key in (
        f"{ACC}:{TH}",
        f"{ACC}:{TH_KHAC}",
        "patient:11111111-1111-1111-1111-111111111111:acc-1",
    ):
        await rig.env.execute(
            "INSERT INTO agent.proactive_send_counters (clinic_id, scope_key, day_key, count) "
            "VALUES (:c, :k, '2026-09-20', 2)",
            c=rig.clinic_id,
            k=scope_key,
        )

    result = await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)

    remaining = await rig.env.fetch("SELECT scope_key FROM agent.proactive_send_counters ORDER BY scope_key")
    assert [r["scope_key"] for r in remaining] == [
        f"{ACC}:{TH_KHAC}",
        "patient:11111111-1111-1111-1111-111111111111:acc-1",
    ]
    assert result.proactive_counters == 1


async def test_wipe_thread_context_keeps_scheduled_jobs_because_they_are_promises_to_the_user(
    rig: Rig,
) -> None:
    """(thêm) lịch hẹn là LỜI ĐÃ HỨA với người dùng: reset ngữ cảnh không nuốt nó"""
    await rig.env.execute(
        "INSERT INTO agent.jobs (clinic_id, id, account_id, thread_id, thread_type, name, kind, payload, "
        "schedule_kind, run_at, max_runs) VALUES (:c, 'job-1', :a, :t, 0, 'nhắc', 'message', '{}', 'once', "
        "'2030-01-01T00:00:00Z', 1)",
        c=rig.clinic_id,
        a=ACC,
        t=TH,
    )
    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)
    assert await rig.env.scalar("SELECT COUNT(*) FROM agent.jobs WHERE id = 'job-1'") == 1


# ----------------------------------------------------------------- trí nhớ chỉ xóa khi được tick


async def _memory_count(rig: Rig, account_id: str) -> int:
    return len(await rig.memories.list_memories(rig.clinic_id, account_id=account_id, limit=50))


async def test_wipe_memories_default_keeps_memory_because_it_belongs_to_the_person_not_the_chat(
    rig: Rig,
) -> None:
    """xoaNguCanhThread - trí nhớ chỉ xóa khi được tick: MẶC ĐỊNH giữ trí nhớ - nó gắn với con người, không gắn với hội thoại"""
    before = await _memory_count(rig, ACC)
    result = await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)

    assert result.memories == 0
    assert await _memory_count(rig, ACC) == before, "không tick thì tuyệt đối không đụng trí nhớ"


async def test_wipe_memories_ticked_deletes_the_facts_learned_in_this_thread(rig: Rig) -> None:
    """xoaNguCanhThread - trí nhớ chỉ xóa khi được tick: tick thì xóa fact học TRONG thread này"""
    result = await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH, WipeOptions(wipe_memories=True))
    assert result.memories == 1


async def test_wipe_memories_ticked_still_keeps_facts_learned_in_other_threads_about_the_same_person(
    rig: Rig,
) -> None:
    """xoaNguCanhThread - trí nhớ chỉ xóa khi được tick: tick vẫn GIỮ fact học ở thread khác về cùng người"""
    # Lọc theo ``learned_in_thread_id``: cùng subject nhưng học ở nơi khác thì người dùng không hề yêu cầu bỏ.
    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH, WipeOptions(wipe_memories=True))
    remaining = await rig.memories.list_memories(rig.clinic_id, account_id=ACC, limit=50)
    assert any(TH_KHAC in m.content for m in remaining), "fact của thread khác phải còn"


# ----------------------------------------------------------------- khóa phiên router


async def test_wipe_epoch_every_wipe_bumps_the_epoch_so_the_router_opens_a_new_session(rig: Rig) -> None:
    """xoaNguCanhThread - khóa phiên router: mỗi lần xóa tăng epoch, nên router mở phiên MỚI"""
    before = await rig.threads.get_thread_context_epoch(rig.clinic_id, ACC, TH)
    first = (await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)).new_epoch
    second = (await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)).new_epoch

    assert first == before + 1
    assert second == before + 2, "xóa hai lần phải ra hai phiên khác nhau"
    assert await rig.threads.get_thread_context_epoch(rig.clinic_id, ACC, TH) == second, (
        "phải đọc lại được từ DB"
    )


async def test_wipe_epoch_does_not_bump_the_epoch_of_another_thread(rig: Rig) -> None:
    """xoaNguCanhThread - khóa phiên router: KHÔNG tăng epoch của thread khác"""
    before = await rig.threads.get_thread_context_epoch(rig.clinic_id, ACC, TH_KHAC)
    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)
    assert await rig.threads.get_thread_context_epoch(rig.clinic_id, ACC, TH_KHAC) == before


# ----------------------------------------------------------------- ảnh trên đĩa và mô tả ảnh


async def test_wipe_images_deletes_the_files_and_the_image_descriptions_of_that_thread(rig: Rig) -> None:
    """xoaNguCanhThread - ảnh trên đĩa và mô tả ảnh: xóa file ảnh VÀ mô tả ảnh của thread đó"""
    of_thread = await rig.seed_image(ACC, TH, "a-0.jpg")
    of_other = await rig.seed_image(ACC, TH_KHAC, "b-0.jpg")

    result = await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)

    assert result.images == 1
    assert result.image_descriptions == 1
    assert rig.image_exists(of_thread) is False, "file phải bị xóa"
    assert await rig.image_desc.get_image_description(rig.clinic_id, of_thread) is None, "mô tả phải bị xóa"
    assert rig.image_exists(of_other) is True, "ảnh thread khác phải còn"
    assert await rig.image_desc.get_image_description(rig.clinic_id, of_other) == "mô tả ảnh", (
        "mô tả thread khác phải còn"
    )


async def test_wipe_images_thread_that_never_had_images_returns_zero_without_blowing_up(rig: Rig) -> None:
    """xoaNguCanhThread - ảnh trên đĩa và mô tả ảnh: thread chưa từng có ảnh thì không nổ, trả 0"""
    result = await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH_KHAC)
    assert result.images == 0
    assert result.image_descriptions == 0


# ----------------------------------------------------------------- trace agent


async def test_wipe_trace_deletes_the_steps_of_the_turns_of_that_thread_leaving_no_orphan_steps(
    rig: Rig,
) -> None:
    """xoaNguCanhThread - trace agent: xóa step theo turn, không để step mồ côi"""
    turn_id = await rig.usage.open_agent_turn(rig.clinic_id, ACC, TH)
    await rig.traces.save_turn_trace(
        rig.clinic_id,
        turn_id,
        [
            StepTrace(
                step_number=1,
                attempt=1,
                text="nội dung nhạy cảm của người dùng",
                finish_reason="stop",
                input_tokens=10,
                output_tokens=5,
            )
        ],
    )
    assert len(await rig.traces.get_turn_trace(rig.clinic_id, turn_id)) > 0, "phải gieo được trace trước đã"

    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)

    assert await rig.traces.get_turn_trace(rig.clinic_id, turn_id) == [], (
        "trace chứa nguyên văn tin, phải xóa theo"
    )
    leftover = await rig.env.scalar("SELECT COUNT(*) FROM agent.usage_steps WHERE turn_id = :t", t=turn_id)
    assert leftover == 0, "step mồ côi là dữ liệu nằm lại mà không giao diện nào thấy"


async def test_wipe_does_not_delete_the_trace_of_another_thread(rig: Rig) -> None:
    """(thêm) trace của thread khác còn nguyên"""
    other_turn = await rig.usage.open_agent_turn(rig.clinic_id, ACC, TH_KHAC)
    await rig.traces.save_turn_trace(
        rig.clinic_id, other_turn, [StepTrace(step_number=1, attempt=1, text="của thread khác")]
    )
    await rig.wiper.wipe_thread_context(rig.clinic_id, ACC, TH)
    assert len(await rig.traces.get_turn_trace(rig.clinic_id, other_turn)) == 1
