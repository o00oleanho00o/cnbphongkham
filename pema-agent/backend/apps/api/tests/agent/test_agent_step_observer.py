# ported from: src/agent/agent-step-observer.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original needed ``setupTestEnv`` + a dynamic import because ``runtime-tuning-settings`` touched SQLite
at module scope. Here the tuning API is a plain in-memory provider: the defaults (``AGENT_TRACE_ENABLED``
true, ``AGENT_TRACE_MAX_CHARS`` 500) apply and each test starts from a reset provider.

Deviations of the translation: ``forLog(undefined)`` -> ``for_log(None)`` gives ``"null"`` (JS
``undefined`` has no Python counterpart); the extra ``test_..._log_khong_chua_noi_dung`` cases pin the
no-PII-in-logs deviation described in the module docstring of ``agent_step_observer``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from pema.agent.agent_step_observer import for_log, tao_quan_sat_step
from pema.agent.model_types import RawStep, StepContentPart, ToolCallPart, ToolResultPart
from pema.agent.tool_loop_guard import NguongGuard, ToolLoopGuard
from pema.config.runtime_tuning_settings import reset_tuning_provider
from pema_contracts.agent_turn import StepTrace

NGUONG = NguongGuard(chan_loi_giong_het=5, chan_cung_tool_loi=8, chan_khong_tien_trien=5)


def la_tool_chi_doc(t: str) -> bool:
    return t == "web_fetch"


def ket_qua_loi(thong_diep: str) -> dict[str, Any]:
    return {"ok": False, "loi": thong_diep}


@pytest.fixture(autouse=True)
def _clean_provider() -> Iterator[None]:
    reset_tuning_provider()
    yield
    reset_tuning_provider()


# --- forLog - nhánh hỏng hiện CÂU, không hiện vỏ JSON --------------------------------------------------


def test_for_log_nhanh_hong_hien_cau_ket_qua_danh_dau_hong_ra_cau_tieng_viet_doc_duoc() -> None:
    """kết quả đánh dấu hỏng ra câu tiếng Việt đọc được"""
    ra = for_log(ket_qua_loi('Không có file "bao-gia.pdf" trong kho shared-files'), 300)
    # The JSON shell escapes quotes twice and eats ~20 chars of the ceiling - and the part that gets cut is
    # exactly the part saying why it failed
    assert '\\"' not in ra, f"không được escape ngoặc kép: {ra}"
    assert '{"ok"' not in ra, f"không được lộ vỏ JSON: {ra}"
    assert 'Không có file "bao-gia.pdf"' in ra


def test_for_log_nhanh_hong_hien_cau_chuoi_tran_va_object_thuong_van_nhu_cu() -> None:
    """chuỗi trần và object thường vẫn như cũ"""
    assert for_log("nội dung trang", 300) == "nội dung trang"
    assert for_log({"url": "https://a.test"}, 300) == '{"url":"https://a.test"}'
    assert for_log(None, 300) == "null"


def test_for_log_nhanh_hong_hien_cau_van_cat_theo_tran() -> None:
    """vẫn cắt theo trần"""
    ra = for_log(ket_qua_loi("x" * 500), 50)
    assert len(ra) <= 53, f"phải cắt: {len(ra)} ký tự"
    assert ra.endswith("...")


# --- taoQuanSatStep - lỗi bên trong KHÔNG được thoát ra ------------------------------------------------
# Vital invariant. ``notify()`` of ai@7.0.37 calls the callback in an EMPTY ``try {...} catch (e) {}``, so
# if the observer throws the SDK swallows everything: the guard stops counting, the trace stops recording,
# the log says nothing. We must catch ourselves to leave one ERROR line - and so ``run_agent_turn`` does
# not depend on whether the loop swallows it (a later version changing the behaviour kills the whole turn).


class _GuardHong(ToolLoopGuard):
    def ghi_nhan(self, step: RawStep) -> Any:
        raise RuntimeError("guard vỡ")


def test_tao_quan_sat_step_loi_ben_trong_khong_duoc_thoat_ra_guard_nem_thi_handler_nuot_lai() -> None:
    """guard ném thì handler nuốt lại, không ném ra ngoài"""
    guard_hong = _GuardHong(NGUONG, la_tool_chi_doc)
    quan_sat = tao_quan_sat_step(guard=guard_hong, trace=[], lay_lan_chay=lambda: 1)
    quan_sat(RawStep(tool_results=[], content=[]))


def test_tao_quan_sat_step_loi_ben_trong_khong_duoc_thoat_ra_step_co_hinh_dang_la_cung_khong_nem() -> None:
    """step có hình dạng lạ cũng không ném"""
    guard = ToolLoopGuard(NGUONG, la_tool_chi_doc)
    quan_sat = tao_quan_sat_step(guard=guard, trace=[], lay_lan_chay=lambda: 1)
    for step in (
        RawStep(),
        RawStep(tool_results=[]),
        RawStep(content=[]),
        RawStep(tool_calls=[ToolCallPart(input={"a": object()})]),
    ):
        quan_sat(step)


def test_tao_quan_sat_step_loi_ben_trong_khong_duoc_thoat_ra_luot_chay_duoc_thi_van_dem_cho_guard_va_day_trace_ra_mang_cua_caller() -> (
    None
):
    """lượt chạy được thì vẫn đếm cho guard và đẩy trace ra mảng của caller

    The control for the two cases above: wrapping in try/except must not swallow the real work as well.
    """
    guard = ToolLoopGuard(
        NguongGuard(chan_loi_giong_het=2, chan_cung_tool_loi=8, chan_khong_tien_trien=5), la_tool_chi_doc
    )
    trace: list[StepTrace] = []
    quan_sat = tao_quan_sat_step(guard=guard, trace=trace, lay_lan_chay=lambda: 1)

    step = RawStep(
        tool_results=[ToolResultPart(tool_name="web_fetch", input={"url": "x"}, output=ket_qua_loi("hỏng"))],
        content=[],
    )
    quan_sat(step)
    assert guard.da_chan() is False, "mới một lần"
    quan_sat(step)
    assert guard.da_chan() is True, "lần hai chạm ngưỡng - guard vẫn được nuôi"
    assert len(trace) == 2, "trace phải ra mảng của caller"


# --- Additions pinning the deviations of this port -----------------------------------------------------


def test_tao_quan_sat_step_lay_lan_chay_doc_luc_goi_khong_phai_luc_dung() -> None:
    """lanChay đọc LÚC GỌI: lần chạy tăng giữa lượt thì trace ghi đúng nhãn của lần đó"""
    guard = ToolLoopGuard(NGUONG, la_tool_chi_doc)
    trace: list[StepTrace] = []
    lan = [1]
    quan_sat = tao_quan_sat_step(guard=guard, trace=trace, lay_lan_chay=lambda: lan[0])
    quan_sat(RawStep(step_number=0))
    lan[0] = 2
    quan_sat(RawStep(step_number=0))
    assert [t.attempt for t in trace] == [1, 2]
    assert [t.step_number for t in trace] == [1, 1]


def test_tao_quan_sat_step_tat_agent_trace_enabled_thi_khong_day_trace_nhung_guard_van_dem() -> None:
    """AGENT_TRACE_ENABLED tắt thì không đẩy trace, guard vẫn được nuôi"""
    from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider

    install_tuning_provider(StaticTuningProvider({"AGENT_TRACE_ENABLED": False}))
    guard = ToolLoopGuard(
        NguongGuard(chan_loi_giong_het=2, chan_cung_tool_loi=8, chan_khong_tien_trien=5), la_tool_chi_doc
    )
    trace: list[StepTrace] = []
    quan_sat = tao_quan_sat_step(guard=guard, trace=trace, lay_lan_chay=lambda: 1)
    step = RawStep(
        tool_results=[ToolResultPart(tool_name="web_fetch", input={"url": "x"}, output=ket_qua_loi("hỏng"))]
    )
    quan_sat(step)
    quan_sat(step)
    assert trace == []
    assert guard.da_chan() is True


def test_tao_quan_sat_step_log_khong_chua_noi_dung_tool_hay_van_ban_cua_buoc(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """log không chứa nội dung tool, văn bản hay lập luận của step (không PII trong log)"""
    # ``configure_logging`` (test_logger) leaves the ``pema`` logger non-propagating; caplog sits on the root
    monkeypatch.setattr(logging.getLogger("pema"), "propagate", True)
    bi_mat = "BENH-NHAN-GIA-0000"
    guard = ToolLoopGuard(NGUONG, la_tool_chi_doc)
    quan_sat = tao_quan_sat_step(guard=guard, trace=[], lay_lan_chay=lambda: 1)
    with caplog.at_level(logging.DEBUG, logger="pema"):
        quan_sat(
            RawStep(
                text=f"xin chào {bi_mat}",
                reasoning_text=f"nghĩ về {bi_mat}",
                tool_calls=[ToolCallPart(tool_name="web_fetch", input={"url": bi_mat})],
                tool_results=[
                    ToolResultPart(
                        tool_name="web_fetch",
                        input={"url": bi_mat, "fileName": f"{bi_mat}.pdf", "mode": "doc"},
                        output=f"nội dung {bi_mat}",
                    )
                ],
                content=[
                    StepContentPart(
                        type="tool-error", tool_name="send_file", input={"q": bi_mat}, error=Exception(bi_mat)
                    )
                ],
            )
        )
    assert caplog.records, "phải có log để kiểm"
    for record in caplog.records:
        da_ghi = json.dumps(
            {"msg": record.getMessage(), "fields": getattr(record, "pema_fields", {})},
            ensure_ascii=False,
            default=str,
        )
        assert bi_mat not in da_ghi, da_ghi
    tool_da_chay = next(r for r in caplog.records if r.getMessage() == "Tool đã chạy")
    fields: dict[str, Any] = getattr(tool_da_chay, "pema_fields", {})
    assert fields["tool"] == "web_fetch"
    assert fields["args"] == {"mode": "doc", "fileName_chars": len(f"{bi_mat}.pdf")}
    assert fields["output_chars"] == len(f"nội dung {bi_mat}")
