# ported from: src/agent/run-agent-turn.test.ts
"""Tests of the LOOP itself, not of the two pure decision functions (those are in ``test_agent_loop``).

Before, the wiring (glitch retry, dropping pixels when the provider refuses, the wrap-up call at the step
ceiling) had no test, and those are exactly the branches that run only when everything is failing.

The model is injected, so no network request. Differences forced by the port: the tool registry is
``FakeToolRegistry`` (the real one is package D4's), the model is ``ScriptedModel`` (``ChatModel.complete``
replaces ``MockLanguageModelV4.doStream``), a provider error is a ``ProviderCallError``, and the engine raises
``AgentTurnError`` with the original exception in ``__cause__`` (the original asserted on the raw error).
Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from pema.agent.history_to_model_messages import StoredImage
from pema.agent.model_types import ModelCompletion
from pema.agent.providers.errors import ProviderCallError
from pema.agent.streaming_model_test_helper import (
    goi_tool,
    prompt_tail,
    prompt_text,
    rong,
    tool_keys,
    tra_loi,
)
from pema.agent.testing_engine import ACCOUNT_ID, EngineHarness, TurnRun, tin_nhan
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.agent_turn import TurnCallbacks
from pema_contracts.channel import InboundImage, InboundMessage
from pema_contracts.turn_errors import AgentTurnError, ProviderErrorKind


class Tuning:
    """``setTuning`` of the original tests: a dict behind a ``StaticTuningProvider``."""

    def __init__(self) -> None:
        self.values: dict[str, str | int | float | bool] = {}
        self.provider = StaticTuningProvider(self.values)

    def set(self, key: str, value: str | int | float | bool | None) -> None:
        if value is None:
            self.values.pop(key, None)
        else:
            self.values[key] = value
        self.provider.replace(self.values)


@pytest.fixture
def tuning() -> Iterator[Tuning]:
    # Ceiling of 2 steps: enough to build both the "hit the ceiling" branch and the "later step throws"
    # branch without simulating 8 rounds.
    t = Tuning()
    t.set("LLM_MAX_STEPS", 2)
    install_tuning_provider(t.provider)
    yield t
    reset_tuning_provider()


def loi_api(status: int, message: str) -> ProviderCallError:
    return ProviderCallError(message, status_code=status, response_body=message)


def goi_tool_ma() -> ModelCompletion:
    """An unknown tool: the loop produces a ``tool-error`` content part (NOT in ``tool_results``), the source
    the guard must read. Calling it identically several times is the ``loi-giong-het`` branch."""
    return goi_tool("tool_khong_ton_tai", call_id="c")


def goi_send_file(source: str = "khong-co-file-nay.pdf") -> ModelCompletion:
    return goi_tool("send_file", {"source": source}, call_id="c")


def chen_o_lan_thu(lan_can_chen: int, text: str = "cho-minh-doi-thanh-file-word-nhe") -> Any:
    """``prepareStep`` runs before EVERY step, the first included: a message that arrives mid-turn is
    simulated by returning nothing at the first ask and the message at a later one."""
    state = {"lan": 0}

    async def fetch() -> Sequence[InboundMessage]:
        state["lan"] += 1
        return [tin_nhan(text, msg_id="m-chen")] if state["lan"] == lan_can_chen else []

    return fetch


def traces_attempt_steps(run: TurnRun) -> list[tuple[int, int]]:
    return [(t.attempt, t.step_number) for t in run.trace]


# --------------------------------------------------------------------------------------------- normal turn


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_luot_binh_thuong_tra_text_cua_model_va_cong_dung_usage() -> None:
    """trả text của model và cộng đúng usage"""
    run = await EngineHarness().run([lambda: tra_loi("Hôm nay thứ tư.")])
    assert run.result.text == "Hôm nay thứ tư."
    assert run.result.usage.total_tokens == 150
    assert run.result.usage.steps == 1


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_luot_binh_thuong_day_trace_vao_mang_cua_caller() -> None:
    """đẩy trace vào mảng của CALLER, không giữ riêng"""
    run = await EngineHarness().run([lambda: tra_loi("xong")])
    assert len(run.trace) == 1, "caller phải nhìn thấy step vừa chạy"
    assert run.trace[0].step_number == 1, "step đánh số từ 1, không phải từ 0"


# ------------------------------------------------------------------------------- router empty completion


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_router_rong_lan_dau_thi_thu_lai_lay_ket_qua_lan_hai() -> None:
    """rỗng lần đầu thì thử lại, lấy kết quả lần hai"""
    run = await EngineHarness().run([rong, lambda: tra_loi("lần hai có chữ")])
    assert run.model.count == 2, "phải gọi lại đúng 1 lần"
    assert run.result.text == "lần hai có chữ"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_router_rong_ca_hai_lan_thi_tra_cau_bao_loi_khong_im_lang() -> None:
    """rỗng cả hai lần thì trả câu báo lỗi, không im lặng bỏ treo"""
    run = await EngineHarness().run([rong])
    assert run.model.count == 2, "thử lại đúng 1 lần rồi thôi, không lặp vô hạn"
    assert len(run.result.text) > 0, "phải nói gì đó cho người nhắn"
    assert run.result.usage.total_tokens == 0


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_router_rong_trace_cua_ca_hai_lan_chay_noi_vao_nhau() -> None:
    """trace của CẢ hai lần chạy nối vào nhau - lúc hỏng mới cần nhìn đủ"""
    run = await EngineHarness().run([rong, lambda: tra_loi("ok")])
    assert len(run.trace) == 2


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_router_rong_hai_lan_chay_danh_dau_attempt_khac_nhau() -> None:
    """hai lần chạy đánh dấu attempt khác nhau, không trộn thành model-đang-lặp

    Both are step 1 because each run numbers again from the start: ``attempt`` is the ONLY thing that tells
    them apart, without it one reads "step 1, step 1".
    """
    run = await EngineHarness().run([rong, lambda: tra_loi("ok")])
    assert traces_attempt_steps(run) == [(1, 1), (2, 1)]


# ------------------------------------------------------------------------------ repair by provider error


async def test_run_agent_turn_chua_loi_401_dung_ngay_khong_chong_them_lan_thu_nao() -> None:
    """401 dừng ngay - KHÔNG chồng thêm lần thử nào lên trên SDK

    The SDK never retried a 401. The invariant: the repair branch must NOT add a try either: a wrong key fails
    however many times, it is only slower.
    """
    model_calls = {"n": 0}

    def fail() -> Exception:
        model_calls["n"] += 1
        return loi_api(401, "Invalid API key")

    with pytest.raises(AgentTurnError) as caught:
        await EngineHarness().run([fail])
    assert model_calls["n"] == 1, "gọi đúng một lần"
    assert caught.value.kind is ProviderErrorKind.AUTH


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_chua_loi_429_dai_dang_chua_them_mot_vong_nua_len_tren_phan_sdk_tu_thu() -> None:
    """429 dai dẳng: chữa THÊM một vòng nữa lên trên phần SDK tự thử

    Without the repair branch it stops at 3 (1 call + 2 retries). With it: wait ``Retry-After`` then run
    ``run_once`` again, and that run again gets 3 tries.
    """
    sdk_tu_thu = 3
    calls = {"n": 0}

    def fail() -> Exception:
        calls["n"] += 1
        return loi_api(429, "Rate limit exceeded")

    with pytest.raises(AgentTurnError):
        await EngineHarness().run([fail])
    assert calls["n"] == sdk_tu_thu * 2, f"mong {sdk_tu_thu * 2} lần gọi, nhận {calls['n']}"


async def test_run_agent_turn_chua_loi_tran_ngu_canh_cat_sau_hon_roi_thu_lai_lan_hai_gui_it_tin_hon(
    tuning: Tuning,
) -> None:
    """tràn ngữ cảnh: cắt sâu hơn rồi thử lại, lần hai gửi ÍT tin hơn

    A SEPARATE thread: 12 long messages stuffed here must not leak into another test. The ceiling is wide
    enough that the first call is not cut, but HALF of it is: exactly what the ``context_overflow`` branch does.
    """
    harness = EngineHarness()
    for i in range(12):
        harness.conversation.add_message(
            ACCOUNT_ID,
            "thread-tran-context",
            content=f"tin dài số {i} " * 200,
            sender_name="Hải",
            sender_id="user-1",
        )
    tuning.set("LLM_CONTEXT_WINDOW", 20_000)
    state = {"lan": 0}

    def step() -> ModelCompletion | Exception:
        state["lan"] += 1
        return (
            loi_api(400, "prompt is too long: 210000 tokens")
            if state["lan"] == 1
            else tra_loi("cắt bớt rồi trả lời được")
        )

    run = await harness.run([step], [tin_nhan(thread_id="thread-tran-context")])
    assert state["lan"] == 2, "thử lại đúng 1 lần"
    assert len(run.model.calls[1].messages) < len(run.model.calls[0].messages)
    assert run.result.text == "cắt bớt rồi trả lời được"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_chua_loi_5xx_van_nem_ra_ngoai_cho_caller_bao_nguoi_dung_khong_nuot() -> None:
    """5xx vẫn ném ra ngoài cho caller báo người dùng, không nuốt"""
    with pytest.raises(AgentTurnError) as caught:
        await EngineHarness().run([lambda: loi_api(503, "Upstream unavailable")])
    assert caught.value.kind is ProviderErrorKind.TRANSIENT


# ----------------------------------------------------------------------------------- step ceiling reached


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_cham_tran_step_het_step_thi_chay_luot_chot_khong_cap_tool() -> None:
    """hết step khi model còn gọi tool thì chạy lượt chốt KHÔNG cấp tool

    Ceiling 2: two tool calls hit the ceiling, request 3 is the wrap-up call.
    """
    run = await EngineHarness().run([goi_tool, goi_tool, lambda: tra_loi("Chốt lại: hôm nay thứ tư.")])
    assert run.model.count == 3, "2 step + 1 lượt chốt"
    assert len(run.model.calls[0].tools) > 0, "lượt thường phải có tool"
    assert len(run.model.calls[2].tools) == 0, (
        "lượt chốt KHÔNG được cấp tool - còn tool thì model lại gọi tiếp và rơi vào đúng cái bẫy vừa thoát"
    )
    assert run.result.text == "Chốt lại: hôm nay thứ tư."


async def test_run_agent_turn_cham_tran_step_guard_chong_lap_dung_vong_truoc_tran_step_va_van_chay_luot_chot(
    tuning: Tuning,
) -> None:
    """GUARD chống lặp dừng vòng TRƯỚC trần step, và vẫn chạy lượt chốt

    The step ceiling is HIGH (8) and the guard threshold LOW (2), so only the guard can stop the loop. With both
    at 2 the test would pass even if the guard were not wired.
    """
    tuning.set("LLM_MAX_STEPS", 8)
    tuning.set("TOOL_LOOP_SAME_ARGS_BLOCK", 2)
    run = await EngineHarness().run(
        [goi_tool_ma, goi_tool_ma, lambda: tra_loi("Mình chưa tra được, nói thật với anh.")]
    )
    assert run.model.count == 3, f"guard phải dừng ở step 2 (+1 lượt chốt), chạy {run.model.count} lần"
    assert len(run.model.calls[-1].tools) == 0, "lần gọi cuối phải là lượt chốt (không tool)"
    assert run.result.text == "Mình chưa tra được, nói thật với anh."


async def test_run_agent_turn_cham_tran_step_tool_ghi_hong_lap_lai_cung_bi_guard_chan(tuning: Tuning) -> None:
    """tool GHI hỏng lặp lại cũng bị guard chặn - đường DUY NHẤT là kết quả đánh dấu hỏng

    A REAL tool: ``send_file`` with a file not in the store returns the failure shape; it does NOT raise so there
    is no ``tool-error`` part, and as a WRITE tool the "no progress" rule does not apply either.
    """
    tuning.set("LLM_MAX_STEPS", 8)
    tuning.set("TOOL_LOOP_SAME_ARGS_BLOCK", 2)
    run = await EngineHarness().run(
        [goi_send_file, goi_send_file, lambda: tra_loi("Không tìm thấy file đó, anh gửi lại giúp em nhé.")]
    )
    assert run.model.count == 3, f"guard phải dừng ở step 2 (+1 lượt chốt), chạy {run.model.count} lần"
    assert len(run.model.calls[-1].tools) == 0, "lần cuối phải là lượt chốt"
    assert run.result.text == "Không tìm thấy file đó, anh gửi lại giúp em nhé."


async def test_run_agent_turn_cham_tran_step_tool_doc_hong_lap_lai_vao_bo_dem_loi_khong_phai_khong_tien_trien(
    tuning: Tuning,
) -> None:
    """tool ĐỌC hỏng lặp lại vào bộ đếm LỖI chứ không phải bộ không-tiến-triển

    ``get_group_info`` in a private chat always returns the failure shape. As a READ tool BOTH counters can
    reach it, told apart by THRESHOLD: same-args error = 2, no-progress = 6. Blocking at step 2 proves the ERROR
    counter; at step 6 it would still be the old branch.
    """
    tuning.set("LLM_MAX_STEPS", 8)
    tuning.set("TOOL_LOOP_SAME_ARGS_BLOCK", 2)
    tuning.set("TOOL_LOOP_NO_PROGRESS_BLOCK", 6)

    def goi_group_info() -> ModelCompletion:
        return goi_tool("get_group_info", call_id="c")

    run = await EngineHarness().run([goi_group_info, goi_group_info, lambda: tra_loi("Đây là chat riêng.")])
    assert run.model.count == 3, f"phải chặn ở step 2 theo bộ đếm LỖI, nhận {run.model.count} lần gọi"
    # The LIFE-OR-DEATH assertion: the mock answers ``stop`` from the third element on, so the loop would end at
    # call 3 even without the guard. The wrap-up only exists when something cut the model mid tool call, and it
    # is the only call without tools.
    assert len(run.model.calls[-1].tools) == 0, "lần cuối phải là LƯỢT CHỐT (không cấp tool)"


async def test_run_agent_turn_cham_tran_step_nguong_guard_bi_kep_theo_tran_step(tuning: Tuning) -> None:
    """ngưỡng guard bị KẸP theo trần step - ngưỡng vượt trần vẫn phải nổ được

    ``nguong_theo_tran_step`` has its own unit test, but whether it is CALLED is watched by nobody: the shape
    of the original bug (a correct function nobody wired). Ceiling 4, same-tool threshold 9: unclamped the
    counter never reaches 9; clamped it becomes 3 and the guard blocks at step 3.
    """
    counter = {"n": 0}

    def goi_send_file_khac() -> ModelCompletion:
        counter["n"] += 1
        return goi_send_file(f"khong-co-{counter['n']}.pdf")

    tuning.set("LLM_MAX_STEPS", 4)
    tuning.set("TOOL_LOOP_SAME_TOOL_BLOCK", 9)
    tuning.set("TOOL_LOOP_SAME_ARGS_BLOCK", 30)
    tuning.set("TOOL_LOOP_NO_PROGRESS_BLOCK", 30)
    run = await EngineHarness().run(
        [goi_send_file_khac, goi_send_file_khac, goi_send_file_khac, lambda: tra_loi("chốt")]
    )
    assert run.model.count == 4, f"guard phải chặn ở step 3 (+1 lượt chốt), nhận {run.model.count}"
    assert len(run.model.calls[-1].tools) == 0, "lần cuối phải là lượt chốt"


async def test_run_agent_turn_cham_tran_step_lan_chay_moi_xoa_sach_bo_dem_guard(tuning: Tuning) -> None:
    """lần chạy MỚI trong cùng lượt xóa sạch bộ đếm guard - không mang tội của lần trước sang

    ``dat_lai()`` is called in 4 places of the loop. Forget it and every turn that must rebuild (overflow,
    throttled, empty router) is blocked wrongly almost at once, exactly when the turn is most fragile.
    """
    tuning.set("LLM_MAX_STEPS", 8)
    tuning.set("TOOL_LOOP_SAME_ARGS_BLOCK", 2)
    state = {"lan": 0}

    def step() -> ModelCompletion | Exception:
        state["lan"] += 1
        if state["lan"] == 1:
            return goi_send_file()  # run 1: first failure
        if state["lan"] == 2:
            return loi_api(400, "prompt is too long: 210000 tokens")  # -> rebuild
        if state["lan"] == 3:
            return goi_send_file()  # run 2: fails again but must count as the FIRST
        return tra_loi("Không gửi được file, em nói thật với anh.")

    run = await EngineHarness().run([step])
    assert run.model.count == 4, "1 step + lỗi tràn + 1 step của lần chạy mới + câu trả lời"
    assert len(run.model.calls[-1].tools) > 0, (
        "lần gọi cuối phải là lượt THƯỜNG - không tool nghĩa là guard chặn oan vì còn giữ bộ đếm của lần trước"
    )


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_cham_tran_step_luot_binh_thuong_khong_bi_guard_dung_toi_doi_chung() -> None:
    """lượt bình thường KHÔNG bị guard đụng tới - đối chứng cho ca trên"""
    run = await EngineHarness().run([goi_tool, lambda: tra_loi("hôm nay thứ tư")])
    assert run.model.count == 2, "không có lượt chốt thừa"
    assert run.result.text == "hôm nay thứ tư"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_cham_tran_step_luot_chot_vao_trace_nhu_mot_lan_chay_rieng() -> None:
    """lượt chốt vào trace như một lần chạy riêng"""
    run = await EngineHarness().run([goi_tool, goi_tool, lambda: tra_loi("chốt")])
    assert [t.attempt for t in run.trace] == [1, 1, 2], "hai step đầu là lần 1, lượt chốt là lần riêng"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_cham_tran_step_luot_chot_cung_loi_thi_van_tra_loi_duoc_khong_nem_ra_ngoai() -> (
    None
):
    """lượt chốt cũng lỗi thì vẫn trả lời được, không ném ra ngoài"""
    run = await EngineHarness().run([goi_tool, goi_tool, lambda: Exception("chốt cũng chết")])
    assert "hỏi lại" in run.result.text, "phải là câu mời hỏi lại, không phải câu tường thuật nội bộ"


# ------------------------------------------------------------------------ provider refuses a turn with image


def _co_anh(run: TurnRun, index: int) -> bool:
    return any(
        isinstance(m.get("content"), list) and any(p.get("type") == "file" for p in m["content"])
        for m in run.model.calls[index].messages
    )


def _harness_voi_anh() -> tuple[EngineHarness, list[InboundMessage]]:
    harness = EngineHarness()
    rel = "media/acc-test/thread-1/anh.jpg"
    harness.images[rel] = StoredImage(base64="/9j/4AAQ", media_type="image/jpeg")
    batch = [tin_nhan(images=[InboundImage(url="https://zalo/x.jpg", local_path=rel)])]
    return harness, batch


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_provider_tu_choi_anh_4xx_voi_luot_dinh_pixel_thi_dung_lai_input_khong_pixel() -> (
    None
):
    """4xx với lượt đính pixel thì dựng lại input KHÔNG pixel và thử lại"""
    harness, batch = _harness_voi_anh()
    state = {"lan": 0}

    def tu_choi() -> Exception:
        return ProviderCallError("model không nhận ảnh", status_code=400, is_retryable=False)

    def tra() -> ModelCompletion:
        state["lan"] += 1
        return tra_loi("Đọc bằng chữ vậy.")

    # The ``Retry`` of the model call does not retry a 400, so exactly two calls reach the model
    run = await harness.run([tu_choi, tra], batch)
    assert _co_anh(run, 0) is True, "lần đầu phải có đính pixel, không thì test này vô nghĩa"
    assert _co_anh(run, 1) is False, "lần thử lại KHÔNG được đính pixel nữa"
    assert run.result.text == "Đọc bằng chữ vậy."
    assert state["lan"] == 1


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_provider_tu_choi_anh_loi_401_sai_key_khong_kich_hoat_bo_pixel() -> None:
    """lỗi 401 (sai key) KHÔNG kích hoạt bỏ pixel - bỏ ảnh cũng không cứu"""
    harness, batch = _harness_voi_anh()
    with pytest.raises(AgentTurnError, match="sai key"):
        await harness.run([lambda: ProviderCallError("sai key", status_code=401)], batch)


# ------------------------------------------------------------------------------------------ turn throws


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_luot_nem_loi_nem_ra_ngoai_nhung_giu_nguyen_trace_cac_step_da_chay() -> None:
    """ném ra ngoài nhưng GIỮ nguyên trace các step đã chạy"""
    cb = TurnCallbacks()
    state = {"lan": 0}

    def step() -> ModelCompletion | Exception:
        state["lan"] += 1
        # Step 1 ran its tool fine (it has a trace), step 2 dies mid-turn
        return (
            goi_tool()
            if state["lan"] == 1
            else ProviderCallError("500 từ router", status_code=500, is_retryable=False)
        )

    with pytest.raises(AgentTurnError, match="500 từ router"):
        await EngineHarness().run([step], callbacks=cb)
    assert len(cb.trace) == 1, "step đã chạy phải còn lại để chẩn đoán, không rơi theo stack"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_luot_nem_loi_nem_loi_goc_cua_provider_khong_phai_vo_boc() -> None:
    """ném LỖI GỐC của provider, không phải vỏ NoOutputGeneratedError của streamText

    The most expensive invariant: losing the HTTP code makes the classifier answer ``unknown`` for everything,
    and a wrong key is told to the sender as "try again in a few minutes". The original exception, with its
    code, is the ``__cause__`` of the ``AgentTurnError`` and the kind is already classified.
    """
    with pytest.raises(AgentTurnError) as caught:
        await EngineHarness().run([lambda: loi_api(401, "Invalid API key")])
    cause = caught.value.__cause__
    assert isinstance(cause, ProviderCallError), f"mong ProviderCallError, nhận {type(cause).__name__}"
    assert cause.status_code == 401, "mã HTTP phải còn nguyên để phân loại được"
    assert caught.value.kind is ProviderErrorKind.AUTH


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_luot_nem_loi_stream_chet_sau_khi_step_1_da_xong_thi_van_nem() -> None:
    """stream chết SAU khi step 1 đã xong thì vẫn ném - không trả kết quả cụt

    A failure at step 2 after step 1 was written must raise: swallowing it sends the turn to the wrap-up call and
    the sender gets "I looked too many steps" while the router is really dead.
    """
    state = {"lan": 0}

    def step() -> ModelCompletion | Exception:
        state["lan"] += 1
        return goi_tool() if state["lan"] == 1 else loi_api(503, "Upstream unavailable")

    with pytest.raises(AgentTurnError, match="Upstream unavailable"):
        await EngineHarness().run([step])


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_luot_nem_loi_sdk_tu_thu_lai_roi_thanh_cong_thi_luot_chay_tiep_binh_thuong() -> (
    None
):
    """SDK tự thử lại rồi THÀNH CÔNG thì lượt chạy tiếp bình thường

    Control for the two above. A failed attempt that a later retry rescues must not kill the whole turn.
    """
    state = {"lan": 0}

    def step() -> ModelCompletion | Exception:
        state["lan"] += 1
        return loi_api(503, "chớp một cái rồi thôi") if state["lan"] == 1 else tra_loi("xong rồi nhé")

    run = await EngineHarness().run([step])
    assert run.result.text == "xong rồi nhé"
    assert state["lan"] >= 2, f"mong gọi lại ít nhất 1 lần, nhận {state['lan']}"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_luot_nem_loi_loi_cua_lan_chay_truoc_khong_giet_lan_chay_sau() -> None:
    """lỗi của lần chạy TRƯỚC không giết lần chạy sau trong cùng lượt

    A persistent 429 burns the 3 tries, then the repair branch waits and runs ``run_once`` again and the model
    answers. Every run has its own state: sharing it would leave the old 429 there and kill the very run that
    saved the turn.
    """
    state = {"lan": 0}

    def step() -> ModelCompletion | Exception:
        state["lan"] += 1
        return loi_api(429, "Rate limit exceeded") if state["lan"] <= 3 else tra_loi("chữa xong, trả lời đây")

    run = await EngineHarness().run([step])
    assert run.result.text == "chữa xong, trả lời đây"


# ---------------------------------------------------------------------------------------------- isolated

DAU_VET_LICH_SU = "cau-chuyen-cu-rat-dac-trung-khong-the-nham-lan"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_isolated_mac_dinh_van_doc_history_luot_tin_nhan_thuong_khong_doi_hanh_vi() -> (
    None
):
    """mặc định (không truyền isolated) vẫn đọc history - lượt tin nhắn thường không đổi hành vi"""
    harness = EngineHarness()
    harness.conversation.add_message(ACCOUNT_ID, "thread-1", content=DAU_VET_LICH_SU)
    run = await harness.run([lambda: tra_loi("ok")])
    assert DAU_VET_LICH_SU in prompt_text(run.model.calls[0]), "history cũ phải có mặt trong prompt gửi model"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_isolated_true_bo_qua_history_luot_theo_lich_khong_doc_hoi_thoai_dang_co() -> (
    None
):
    """isolated:true bỏ qua history - lượt theo lịch không đọc hội thoại đang có của thread"""
    harness = EngineHarness()
    harness.conversation.add_message(ACCOUNT_ID, "thread-1", content=DAU_VET_LICH_SU)
    run = await harness.run([lambda: tra_loi("ok")], isolated=True)
    assert DAU_VET_LICH_SU not in prompt_text(run.model.calls[0]), (
        "history cũ KHÔNG được lọt vào prompt cô lập"
    )


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_isolated_true_giu_nguyen_persona_goc_chi_muc_kha_nang_doi_theo_tool_that_co() -> (
    None
):
    """isolated:true giữ nguyên PERSONA GỐC (base persona, quy tắc an toàn) - chỉ mục 'Khả năng' đổi theo tool thật có

    The base persona (opening sentence, safety rules) stays; the "Khả năng" section is shorter by exactly the
    tools dropped for a scheduled turn (add_reaction, save_memory).
    """
    binh_thuong = await EngineHarness().run([lambda: tra_loi("ok")])
    co_lap = await EngineHarness().run([lambda: tra_loi("ok")], isolated=True)
    text_binh_thuong = binh_thuong.model.calls[0].system
    text_co_lap = co_lap.model.calls[0].system

    assert text_co_lap != text_binh_thuong, "mục Khả năng PHẢI khác nhau - lượt cô lập thiếu tool bị loại"
    assert "Bạn là trợ lý AI trả lời tin nhắn trên Zalo" in text_co_lap, "persona gốc vẫn phải còn nguyên"
    assert "Ghi nhớ lâu dài" not in text_co_lap, "save_memory không được kể trong mục Khả năng khi cô lập"
    # Control uses save_memory and NOT add_reaction: since ``counts_as_capability`` add_reaction is out of the
    # capability section in BOTH turns, so it no longer tells the two branches apart.
    assert "Ghi nhớ lâu dài" in text_binh_thuong, "lượt thường (đối chứng) vẫn phải kể save_memory"
    assert "Thả cảm xúc" not in text_binh_thuong, "add_reaction không đáng khoe ở lượt nào cả"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_isolated_true_loai_add_reaction_save_memory_khoi_schema_tool_gui_model() -> (
    None
):
    """isolated:true loại add_reaction, save_memory khỏi schema tool gửi model"""
    run = await EngineHarness().run([lambda: tra_loi("ok")], isolated=True)
    keys = tool_keys(run.model.calls[0])
    for key in ("add_reaction", "save_memory"):
        assert key not in keys, f"lượt cô lập không được có tool {key}"


@pytest.mark.usefixtures("tuning")
async def test_run_agent_turn_isolated_luot_thuong_van_co_add_reaction_trong_schema_dung_hanh_vi_cu() -> None:
    """lượt thường (isolated mặc định false) VẪN có add_reaction trong schema - đúng hành vi cũ"""
    run = await EngineHarness().run([lambda: tra_loi("ok")])
    assert "add_reaction" in tool_keys(run.model.calls[0]), (
        "lượt tin nhắn thường không bị ảnh hưởng bởi bộ lọc mới"
    )


# ------------------------------------------------------------------------------------ mid-turn injection

DAU_VET_CHEN = "cho-minh-doi-thanh-file-word-nhe"
# Anchor on the MEANING of the label, not its exact words: the wording is still being edited. But do not import
# the constant either: a constant emptied makes ``in ""`` always true and the test useless exactly when needed.
# "đang làm dở" is the only thing that tells the model it is being interrupted and not receiving a new request.
DAU_HIEU_NHAN = "đang làm dở"


@pytest.fixture
def tuning3(tuning: Tuning) -> Tuning:
    # 3 steps: enough to build "inject at step 1, check that steps 2 and 3 still carry it"
    tuning.set("LLM_MAX_STEPS", 3)
    return tuning


async def test_run_agent_turn_tiem_tin_chen_duoc_ngay_truoc_step_dau_tin_toi_trong_luc_con_tai_anh_van_kip(
    tuning3: Tuning,
) -> None:
    """chèn được NGAY TRƯỚC step đầu - tin tới trong lúc còn đang tải ảnh vẫn kịp"""
    run = await EngineHarness().run([lambda: tra_loi("ok")], fetch_injected=chen_o_lan_thu(1))
    assert DAU_VET_CHEN in prompt_text(run.model.calls[0]), "step đầu phải nhận được tin đã đỗ sẵn"


async def test_run_agent_turn_tiem_tin_nhan_them_vao_dung_prompt_cua_step_ke_tiep_kem_nhan(
    tuning3: Tuning,
) -> None:
    """tin nhắn thêm vào ĐÚNG prompt của step kế tiếp, kèm nhãn nói rõ là chen ngang"""
    run = await EngineHarness().run([goi_tool, lambda: tra_loi("ok")], fetch_injected=chen_o_lan_thu(2))
    assert run.model.count >= 2
    assert DAU_VET_CHEN not in prompt_text(run.model.calls[0]), "step ĐẦU chưa được thấy tin chen"
    prompt_sau = prompt_text(run.model.calls[1])
    assert DAU_VET_CHEN in prompt_sau, "step sau phải thấy nội dung tin chen"
    assert DAU_HIEU_NHAN in prompt_sau, "phải kèm nhãn, không thì model đọc nó như một yêu cầu mới hoàn toàn"


async def test_run_agent_turn_tiem_chen_mot_lan_roi_mang_theo_cac_step_sau(tuning3: Tuning) -> None:
    """chèn MỘT lần rồi mang theo các step sau - không phải chèn lại từng step"""
    run = await EngineHarness().run(
        [goi_tool, goi_tool, lambda: tra_loi("xong")], fetch_injected=chen_o_lan_thu(2)
    )
    assert run.model.count >= 3
    prompt = prompt_text(run.model.calls[2])
    assert DAU_VET_CHEN in prompt, "step thứ 3 vẫn phải còn tin chen"
    assert prompt.count(DAU_VET_CHEN) == 1, (
        f"tin chen bị nhân bản {prompt.count(DAU_VET_CHEN)} lần trong prompt"
    )


async def test_run_agent_turn_tiem_khong_co_tin_chen_thi_prompt_khong_dinh_nhan_doi_chung(
    tuning3: Tuning,
) -> None:
    """không có tin chen thì prompt KHÔNG dính nhãn - đối chứng"""

    async def khong_co() -> Sequence[InboundMessage]:
        return []

    run = await EngineHarness().run([goi_tool, lambda: tra_loi("ok")], fetch_injected=khong_co)
    for call in run.model.calls:
        assert DAU_HIEU_NHAN not in prompt_text(call), "không có tin chen mà vẫn dán nhãn là nói dối model"


async def test_run_agent_turn_tiem_lay_tin_chen_nem_loi_thi_luot_van_chay_tron(tuning3: Tuning) -> None:
    """layTinChen NÉM LỖI thì lượt vẫn chạy trọn - đây là nhánh làm tốt thêm, không phải nhánh bắt buộc"""

    async def hong() -> Sequence[InboundMessage]:
        raise RuntimeError("hàng chờ hỏng")

    run = await EngineHarness().run([goi_tool, lambda: tra_loi("vẫn trả lời được")], fetch_injected=hong)
    assert run.result.text == "vẫn trả lời được"


async def test_run_agent_turn_tiem_tat_o_trang_cau_hinh_thi_khong_chen_va_khong_goi_toi_hang_cho(
    tuning3: Tuning,
) -> None:
    """tắt ở trang Cấu hình thì KHÔNG chen, và cũng không gọi tới hàng chờ"""
    tuning3.set("MID_TURN_INJECTION_ENABLED", False)
    state = {"so_lan_lay": 0}

    async def fetch() -> Sequence[InboundMessage]:
        state["so_lan_lay"] += 1
        return [tin_nhan(DAU_VET_CHEN, msg_id="m-chen")]

    run = await EngineHarness().run([goi_tool, lambda: tra_loi("ok")], fetch_injected=fetch)
    assert state["so_lan_lay"] == 0, "tắt rồi thì không được đụng vào hàng chờ - đụng là rút tin ra rồi bỏ đi"
    for call in run.model.calls:
        assert DAU_VET_CHEN not in prompt_text(call)


async def test_run_agent_turn_tiem_tin_chen_song_qua_nhanh_thu_lai_completion_rong(tuning3: Tuning) -> None:
    """tin chen SỐNG QUA nhánh thử lại completion rỗng - không bị đánh rơi

    The queue was already emptied by the fetch, so the message cannot be fetched again. The second run builds
    its context from the ``messages`` variable of the loop, where the injected message never went: without
    re-attaching it the message vanishes for ever (it is in the history but NO turn answers it).
    """
    state = {"so_lan_lay": 0}

    async def fetch() -> Sequence[InboundMessage]:
        state["so_lan_lay"] += 1
        return [tin_nhan(DAU_VET_CHEN, msg_id="m-chen")] if state["so_lan_lay"] == 1 else []

    run = await EngineHarness().run([rong, lambda: tra_loi("lần hai ổn")], fetch_injected=fetch)
    assert run.model.count >= 2
    assert DAU_VET_CHEN in prompt_text(run.model.calls[-1]), "lần chạy SAU retry vẫn phải mang tin chen"


async def test_run_agent_turn_tiem_tin_chen_co_mat_trong_luot_chot(tuning3: Tuning) -> None:
    """tin chen có mặt trong LƯỢT CHỐT - nơi sinh ra câu trả lời gửi xuống Zalo

    A turn that hits the step ceiling goes to the wrap-up and ITS text is what is sent. The longer the turn the
    likelier the ceiling, and only a long turn leaves time for the person to write again: this is the COMMON
    case. Dropping the message there sends an answer to the OLD request.
    """
    tuning3.set("LLM_MAX_STEPS", 2)
    state = {"so_lan_lay": 0}

    async def fetch() -> Sequence[InboundMessage]:
        state["so_lan_lay"] += 1
        return [tin_nhan(DAU_VET_CHEN, msg_id="m-chen")] if state["so_lan_lay"] == 1 else []

    run = await EngineHarness().run([goi_tool], fetch_injected=fetch)
    prompt_chot = prompt_text(run.model.calls[-1])
    assert "trả lời người dùng NGAY BÂY GIỜ" in prompt_chot, "lần gọi cuối phải đúng là lượt chốt"
    assert DAU_VET_CHEN in prompt_chot, "LƯỢT CHỐT PHẢI CÓ TIN CHEN"


async def test_run_agent_turn_tiem_hai_nhanh_chua_loi_noi_nhau_van_chi_mot_ban_tin_chen(
    tuning3: Tuning,
) -> None:
    """HAI nhánh chữa lỗi nối nhau vẫn chỉ MỘT bản tin chen - không cộng dồn

    The re-attach path is not idempotent: assigning back to ``messages`` in each branch gives two identical
    copies after two chained branches, and the model reads "this person repeated themselves". The pair
    ``400 -> empty`` is chosen on purpose: it does not sleep.
    """
    state = {"so_lan_lay": 0, "lan": 0}

    async def fetch() -> Sequence[InboundMessage]:
        state["so_lan_lay"] += 1
        return [tin_nhan(DAU_VET_CHEN, msg_id="m-chen")] if state["so_lan_lay"] == 1 else []

    def step() -> ModelCompletion | Exception:
        state["lan"] += 1
        if state["lan"] == 1:
            return loi_api(400, "prompt is too long")
        if state["lan"] == 2:
            return rong()
        return tra_loi("xong")

    run = await EngineHarness().run([step], fetch_injected=fetch)
    cuoi = prompt_text(run.model.calls[-1])
    assert DAU_VET_CHEN in cuoi, "tin chen phải sống qua cả hai nhánh chữa lỗi"
    assert cuoi.count(DAU_VET_CHEN) == 1, (
        f"tin chen bị nhân thành {cuoi.count(DAU_VET_CHEN)} bản trong prompt cuối"
    )


async def test_run_agent_turn_tiem_sau_nhanh_chua_loi_luot_chot_van_giu_duoc_cau_hoi_goc(
    tuning3: Tuning,
) -> None:
    """sau nhánh chữa lỗi, LƯỢT CHỐT vẫn giữ được CÂU HỎI GỐC

    The wrap-up takes the question as ``messages[-1]``. Assigning the injected message back would make it the
    last element and drop the original question into the cut zone. The context is TIGHT so the wrap-up really
    has to cut: otherwise the question survives even when it falls out of the protected tail and the test is
    green by accident.
    """
    tuning3.set("LLM_MAX_STEPS", 2)
    tuning3.set("LLM_CONTEXT_WINDOW", 4_000)
    state = {"so_lan_lay": 0, "lan": 0}

    def goi_tool_cong_kenh() -> ModelCompletion:
        base = goi_tool()
        base.text = "phần đệm " * 2_000
        return base

    async def fetch() -> Sequence[InboundMessage]:
        state["so_lan_lay"] += 1
        return [tin_nhan(DAU_VET_CHEN, msg_id="m-chen")] if state["so_lan_lay"] == 1 else []

    def step() -> ModelCompletion:
        state["lan"] += 1
        return (
            rong() if state["lan"] == 1 else goi_tool_cong_kenh()
        )  # forces the repair branch, then burns steps

    run = await EngineHarness().run([step], fetch_injected=fetch)
    cuoi = run.model.calls[-1]
    assert "trả lời người dùng NGAY BÂY GIỜ" in prompt_text(cuoi), "lần gọi cuối phải đúng là lượt chốt"
    # The protected tail of the wrap-up is [question, injected message, reminder]: three messages never cut.
    assert tin_nhan().text in prompt_tail(cuoi, 3), (
        "CÂU HỎI GỐC phải nằm trong ĐUÔI ĐƯỢC BẢO VỆ - rơi ra ngoài là model chốt lại mà không biết người ta hỏi gì"
    )


async def test_run_agent_turn_tiem_luot_theo_lich_agent_loop_khong_tu_chan_theo_isolated(
    tuning3: Tuning,
) -> None:
    """lượt theo lịch: agent-loop KHÔNG tự chặn theo isolated - chặn nằm ở call site

    Records the REAL behaviour: an isolated turn does not block it by itself, it just is not given this function
    on the real path. If someone passes it later they must decide whether to block here: this test goes red and
    forces a re-read.
    """
    state = {"so_lan_lay": 0}

    async def fetch() -> Sequence[InboundMessage]:
        state["so_lan_lay"] += 1
        return []

    await EngineHarness().run([goi_tool, lambda: tra_loi("ok")], isolated=True, fetch_injected=fetch)
    assert state["so_lan_lay"] > 0, "hiện tại agent-loop KHÔNG tự chặn theo isolated - chặn nằm ở call site"
