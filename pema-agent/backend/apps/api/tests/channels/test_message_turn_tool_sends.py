# ported from: src/zalo/message-turn-tool-sends.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original ran a model that called the ``send_file`` tool. The tools are package D4 and the loop is D1; the seam this
pipeline owns is ``TurnCallbacks.record_tool_sent`` (``ghiNhanDaGui``): a tool that sent something reports the text and
it must enter the history AT ONCE, between the user's message and the closing answer.
"""

from __future__ import annotations

from pema.channels.pipeline_testing import FakeEngine, TurnRig
from pema_contracts.agent_turn import AgentTurnRequest, AgentTurnResult, TokenUsage, TurnCallbacks

THREAD = "t-tool"
TEN_FILE = "bang-gia-thang-8.xlsx"


def engine_goi_send_file(caption: str, cau_chot: str) -> FakeEngine:
    """Step 1: the tool 'sends' a file and reports it; step 2 closes with text."""

    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        assert callbacks is not None
        assert callbacks.record_tool_sent is not None
        callbacks.record_tool_sent(f"[Đã gửi file {TEN_FILE}] {caption}")
        return AgentTurnResult(text=cau_chot, usage=TokenUsage(total_tokens=75, steps=2))

    return FakeEngine(script=script)


def history(rig: TurnRig) -> list[tuple[str, str]]:
    return rig.conversation.contents(rig.config.id, THREAD)


async def test_process_batch_tin_do_tool_gui_vao_history_file_bot_gui_co_mat_trong_history_kem_ten_file_va_caption() -> (
    None
):
    """file bot gửi có mặt trong history, kèm tên file và caption"""
    rig = TurnRig.create(engine=engine_goi_send_file("Bảng giá đây anh nhé", "Em gửi rồi ạ"))
    await rig.run([await rig.receive("gửi mình bảng giá", "m1", thread_id=THREAD)])

    dong_file = next((row for row in history(rig) if TEN_FILE in row[1]), None)
    assert dong_file is not None, (
        "HISTORY PHẢI CÓ dòng ghi việc đã gửi file - thiếu là dashboard mất tin và lượt sau bot không nhớ đã gửi"
    )
    assert dong_file[0] == "assistant"
    assert "Bảng giá đây anh nhé" in dong_file[1], "phải giữ cả caption"
    assert rig.sent_texts() == ["Em gửi rồi ạ"], "câu chốt đi xuống kênh"


async def test_process_batch_tin_do_tool_gui_vao_history_thu_tu_history_dung() -> None:
    """thứ tự history đúng: tin người dùng -> tin tool gửi -> câu chốt của agent"""
    # Tin người dùng vào lịch sử từ lúc NHẬN, tin do tool gửi ghi ngay lúc gửi, câu chốt ghi sau cùng - ba mốc theo
    # đúng thứ tự thời gian thật.
    rig = TurnRig.create(engine=engine_goi_send_file("Bảng giá đây", "Em gửi rồi ạ"))
    await rig.run([await rig.receive("gửi mình bảng giá", "m1", thread_id=THREAD)])

    rows = history(rig)
    vi_tri_hoi = next(i for i, r in enumerate(rows) if "gửi mình bảng giá" in r[1])
    vi_tri_file = next(i for i, r in enumerate(rows) if TEN_FILE in r[1])
    vi_tri_chot = next(i for i, r in enumerate(rows) if "Em gửi rồi ạ" in r[1])

    assert vi_tri_hoi < vi_tri_file, "tin người dùng phải đứng TRƯỚC tin tool gửi"
    assert vi_tri_file < vi_tri_chot, "tin tool gửi phải đứng TRƯỚC câu chốt của agent"
