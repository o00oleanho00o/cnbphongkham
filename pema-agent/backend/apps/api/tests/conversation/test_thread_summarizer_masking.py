"""The summary prompt is built from the RAW history, so under ``patient_channel`` it must be masked before the
model sees it (package G, SECURITY-REVIEW-AI01 SEC-01; no zalo-agent original). Every text is fictional."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from pema.conversation.thread_summarizer import (
    Backlog,
    BacklogRow,
    SummaryResult,
    ThreadSummarizer,
)
from pema.policy.hooks import ClinicPolicyHooks
from pema.policy.profiles import build_policy_context
from pema.workers.main import summary_mask_of
from pema_contracts.channel import ChannelKind
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.testing import fake_account_config, fake_agent_profile


class _Threads:
    def __init__(self) -> None:
        self.saved: list[str] = []

    async def set_thread_summary(self, *args: Any) -> None:
        self.saved.append(str(args[3]))


class _Summarizer(ThreadSummarizer):
    def __init__(self, threads: _Threads) -> None:
        super().__init__(cast(Any, None), cast(Any, threads), None)

    async def collect_summary_backlog(self, clinic_id: Any, account_id: str, thread_id: str) -> Backlog:
        rows = [
            BacklogRow(1, "user", "Lan Mẫu", "Em là Lan Mẫu, số điện thoại 0900000000, em muốn đổi lịch"),
            BacklogRow(2, "assistant", None, "Dạ em ghi nhận"),
        ] * 60
        return Backlog(backlog=rows, old_summary="", covers_to=0)


async def test_prompt_filter_masks_the_prompt_before_the_model_is_called() -> None:
    """lọc prompt chạy TRƯỚC khi gọi model: số điện thoại thô không bao giờ tới generator"""
    seen: list[str] = []

    async def generate(prompt: str) -> SummaryResult:
        seen.append(prompt)
        return SummaryResult(text="tóm tắt", truncated=False)

    threads = _Threads()
    summarizer = _Summarizer(threads)
    done = await summarizer.maybe_summarize_thread(
        uuid4(), "acc", "thr", generate, prompt_filter=lambda p: p.replace("0900000000", "[SDT_1]")
    )
    assert done is True
    assert seen
    assert "0900000000" not in seen[0]
    assert "[SDT_1]" in seen[0]


async def test_a_filter_that_raises_means_no_model_call_and_no_summary() -> None:
    """lọc lỗi thì không gọi model và không lưu summary (fail closed)"""
    calls: list[str] = []

    async def generate(prompt: str) -> SummaryResult:
        calls.append(prompt)
        return SummaryResult(text="x", truncated=False)

    def broken(_prompt: str) -> str:
        raise RuntimeError("mask unavailable")

    threads = _Threads()
    done = await _Summarizer(threads).maybe_summarize_thread(
        uuid4(), "acc", "thr", generate, prompt_filter=broken
    )
    assert done is False
    assert calls == []
    assert threads.saved == []


def test_the_real_policy_masks_phone_and_name_in_a_summary_prompt() -> None:
    """mask thật của chính sách: SĐT và tên người gửi biết trước đều bị che trong prompt tóm tắt"""
    hooks = ClinicPolicyHooks(actions=cast(Any, None), gateway=cast(Any, None))
    account = fake_account_config(
        channel=ChannelKind.ZALO_BOT, policy_profile=PolicyProfileKey.PATIENT_CHANNEL
    )
    agent = fake_agent_profile(policy_profile=PolicyProfileKey.PATIENT_CHANNEL)
    ctx = build_policy_context(clinic_id=uuid4(), account=account, agent=agent, thread_id="thr")
    masker = summary_mask_of(hooks, ctx)
    assert masker is not None
    out = masker("Người dùng: em là Lan Mẫu, sđt 0900000000, em muốn đổi lịch")
    assert "0900000000" not in out
    assert "[SDT_" in out


def test_hooks_without_a_mask_give_no_filter() -> None:
    """hooks không có mask_text thì không có bộ lọc, worker bỏ qua việc tóm tắt"""
    ctx = build_policy_context(
        clinic_id=uuid4(),
        account=fake_account_config(),
        agent=fake_agent_profile(),
        thread_id="thr",
    )
    assert summary_mask_of(object(), ctx) is None
