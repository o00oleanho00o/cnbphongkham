# ported from: src/agent/agent-step-trace.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module (no env, no DB) so the tests run directly.

Deviation of the translation: JS ``Error`` becomes ``Exception``; ``toolResults[i].hong === undefined``
becomes "the key ``hong`` is absent" (the stored dict only carries ``hong`` when the shape is failed).
"""

from __future__ import annotations

import re
from typing import Any

from pema.agent.agent_step_trace import summarize_step
from pema.agent.model_types import (
    ModelUsage,
    RawStep,
    StepContentPart,
    ToolCallPart,
    ToolResultPart,
)

EMPTY = RawStep()

# --- summarizeStep - lấy đủ thứ cần để chẩn đoán -------------------------------------------------------


def test_summarize_step_giu_text_model_noi_va_danh_so_step_tu_1_cho_nguoi_doc() -> None:
    """giữ text model nói, và đánh số step TỪ 1 cho người đọc

    The SDK numbers from 0. Convert right here so the log, the DB and the UI show one number - converting
    only in the UI makes reading the log back off by one.
    """
    t = summarize_step(RawStep(step_number=0, text="Để mình tra giúp anh"), 500)
    assert t.step_number == 1
    assert t.text == "Để mình tra giúp anh"
    assert summarize_step(RawStep(step_number=4), 500).step_number == 5


def test_summarize_step_giu_reasoning_khi_model_co_tra_deepseek_rong_khi_khong_openai() -> None:
    """giữ reasoning khi model có trả (DeepSeek), rỗng khi không (OpenAI)"""
    assert summarize_step(RawStep(reasoning_text="Ta cần cộng 2 và 3"), 500).reasoning == "Ta cần cộng 2 và 3"
    assert summarize_step(EMPTY, 500).reasoning == ""


def test_summarize_step_ghi_tool_call_kem_tham_so_khong_chi_ghi_ket_qua() -> None:
    """ghi TOOL CALL kèm tham số, không chỉ ghi kết quả

    The old version only logged tool results so nobody knew what the model SENT - the imageIndex case had
    to be deduced backwards from the error sentence.
    """
    t = summarize_step(
        RawStep(
            tool_calls=[ToolCallPart(tool_name="create_image", input={"mode": "ve_moi", "prompt": "con mèo"})]
        ),
        500,
    )
    assert t.tool_calls == [{"name": "create_image", "input": '{"mode":"ve_moi","prompt":"con mèo"}'}]


def test_summarize_step_ghi_warnings_day_la_cho_lo_ra_tham_so_bi_provider_am_tham_bo_qua() -> None:
    """ghi WARNINGS - đây là chỗ lộ ra tham số bị provider âm thầm bỏ qua"""
    t = summarize_step(
        RawStep(warnings=[{"type": "unsupported-setting", "setting": "size", "details": "bị bỏ qua"}]), 500
    )
    assert len(t.warnings) == 1
    assert re.search(r"size", t.warnings[0])
    assert re.search(r"unsupported-setting", t.warnings[0])


def test_summarize_step_ghi_usage_rieng_tung_step_khong_phai_tong_ca_luot() -> None:
    """ghi usage RIÊNG từng step, không phải tổng cả lượt"""
    t = summarize_step(RawStep(usage=ModelUsage(input_tokens=1200, output_tokens=340)), 500)
    assert t.input_tokens == 1200
    assert t.output_tokens == 340


def test_summarize_step_giu_finish_reason_de_biet_step_dung_vi_sao() -> None:
    """giữ finishReason để biết step dừng vì sao"""
    assert summarize_step(RawStep(finish_reason="tool-calls"), 500).finish_reason == "tool-calls"


# --- summarizeStep - cắt ngắn --------------------------------------------------------------------------

DAI = "x" * 2000


def test_summarize_step_cat_ngan_cat_text_reasoning_va_noi_dung_tool_theo_tran() -> None:
    """cắt text, reasoning và nội dung tool theo trần"""
    t = summarize_step(
        RawStep(
            text=DAI,
            reasoning_text=DAI,
            tool_calls=[ToolCallPart(tool_name="web_fetch", input={"url": DAI})],
            tool_results=[ToolResultPart(tool_name="web_fetch", output=DAI)],
        ),
        100,
    )
    for s in (t.text, t.reasoning, t.tool_calls[0]["input"], t.tool_results[0]["output"]):
        assert len(s) <= 120, f"còn {len(s)} ký tự - trần 100 cộng phần đuôi báo cắt"
        assert re.search(r"\.\.\.", s), "phải có dấu hiệu bị cắt, không cắt lén"


def test_summarize_step_cat_ngan_noi_dung_ngan_hon_tran_thi_giu_nguyen_khong_them_dau_ba_cham() -> None:
    """nội dung ngắn hơn trần thì giữ nguyên, không thêm dấu ba chấm"""
    t = summarize_step(RawStep(text="ngắn"), 100)
    assert t.text == "ngắn"


def test_summarize_step_cat_ngan_bao_ro_do_dai_that_khi_cat_biet_minh_dang_mat_bao_nhieu() -> None:
    """báo rõ ĐỘ DÀI THẬT khi cắt - biết mình đang mất bao nhiêu"""
    t = summarize_step(RawStep(text=DAI), 100)
    assert re.search(r"2000", t.text), "phải nói nguyên bản dài bao nhiêu"


# --- summarizeStep - dữ liệu thiếu không được làm chết lượt --------------------------------------------


def test_summarize_step_du_lieu_thieu_step_rong_hoan_toan_van_ra_ban_ghi_hop_le() -> None:
    """step rỗng hoàn toàn vẫn ra bản ghi hợp lệ"""
    t = summarize_step(EMPTY, 500)
    assert t.text == ""
    assert t.reasoning == ""
    assert t.tool_calls == []
    assert t.tool_results == []
    assert t.warnings == []
    assert t.input_tokens == 0
    assert t.step_number == 1, "step rong van dem tu 1"


def test_summarize_step_du_lieu_thieu_input_tool_khong_stringify_duoc_co_vong_lap_van_khong_throw() -> None:
    """input tool không stringify được (có vòng lặp) vẫn không throw"""
    vong: dict[str, Any] = {"a": 1}
    vong["self"] = vong
    t = summarize_step(RawStep(tool_calls=[ToolCallPart(tool_name="x", input=vong)]), 500)
    assert len(t.tool_calls) == 1
    assert len(t.tool_calls[0]["input"]) > 0, "phải có gì đó thay vì rỗng hoặc throw"


# --- summarizeStep - lỗi tool --------------------------------------------------------------------------
# Tool errors are the MOST IMPORTANT class of event the first version missed entirely: the SDK keeps them
# in ``content`` as ``tool-error`` while ``toolResults`` only filters ``type === "tool-result"`` so it is
# always empty when a tool breaks. Measured with ai@7.0.37: a tool raising an exception gives
# ``toolResults.length === 0`` and ``content`` has ``tool-call, tool-error``. Reading it incompletely = the
# bot promises to draw an image, there is no image, and the log and trace are both empty.


def test_summarize_step_loi_tool_nhat_tool_error_tu_content_cho_tool_results_khong_bao_gio_co() -> None:
    """nhặt tool-error từ content, chỗ toolResults không bao giờ có"""
    t = summarize_step(
        RawStep(
            tool_calls=[ToolCallPart(tool_name="create_image", input={"prompt": "x"})],
            tool_results=[],
            content=[
                StepContentPart(type="tool-call", tool_name="create_image"),
                StepContentPart(
                    type="tool-error", tool_name="create_image", error=Exception("prompt vượt 4000 ký tự")
                ),
            ],
        ),
        500,
    )
    assert t.tool_results == [], "SDK không đưa lỗi vào đây - đó chính là cái bẫy"
    assert len(t.tool_errors) == 1
    assert t.tool_errors[0] == {"name": "create_image", "error": "prompt vượt 4000 ký tự"}


def test_summarize_step_loi_tool_lay_duoc_message_cua_error_json_stringify_err_ra_rong_vi_message_non_enumerable() -> (
    None
):
    """lấy được message của Error - JSON.stringify(err) ra {} vì message non-enumerable

    (In Python ``json.dumps`` of an exception raises, so ``str(err)`` is the path.)
    """
    t = summarize_step(
        RawStep(
            content=[StepContentPart(type="tool-error", tool_name="web_fetch", error=Exception("mạng rớt"))]
        ),
        500,
    )
    assert t.tool_errors[0]["error"] == "mạng rớt", "stringify thẳng sẽ ra '{}' - vô dụng"


def test_summarize_step_loi_tool_loi_khong_phai_error_zod_tra_mang_issue_van_doc_duoc() -> None:
    """lỗi không phải Error (Zod trả mảng issue) vẫn đọc được"""
    t = summarize_step(
        RawStep(
            content=[
                StepContentPart(
                    type="tool-error", tool_name="x", error=[{"path": ["mode"], "message": "Required"}]
                )
            ]
        ),
        500,
    )
    assert re.search(r"Required", t.tool_errors[0]["error"])


def test_summarize_step_loi_tool_loi_dai_bi_cat_kem_do_dai_that() -> None:
    """lỗi dài bị cắt kèm độ dài thật"""
    t = summarize_step(
        RawStep(content=[StepContentPart(type="tool-error", tool_name="x", error=Exception("y" * 300))]), 50
    )
    assert re.search(r"\(300 ký tự\)$", t.tool_errors[0]["error"])


def test_summarize_step_loi_tool_step_khong_co_content_van_ra_mang_rong_khong_throw() -> None:
    """step không có content vẫn ra mảng rỗng, không throw"""
    assert summarize_step(RawStep(), 500).tool_errors == []


def test_summarize_step_loi_tool_step_chay_tot_thi_tool_errors_rong_khong_lan_tool_result_vao() -> None:
    """step chạy tốt thì toolErrors rỗng, không lẫn tool-result vào"""
    t = summarize_step(
        RawStep(
            tool_results=[ToolResultPart(tool_name="web_search", output="ok")],
            content=[
                StepContentPart(type="tool-call", tool_name="web_search"),
                StepContentPart(type="tool-result", tool_name="web_search"),
            ],
        ),
        500,
    )
    assert t.tool_errors == []
    assert len(t.tool_results) == 1


# --- summarizeStep - nhánh HỎNG của tool hiện câu, không hiện vỏ JSON ----------------------------------


def test_summarize_step_nhanh_hong_cua_tool_hien_cau_ket_qua_danh_dau_hong_ra_cau_doc_duoc_tren_trang_trace() -> (
    None
):
    """kết quả đánh dấu hỏng ra câu đọc được trên trang Trace

    Letting ``json.dumps`` handle it makes this box show ``{"ok":false,"loi":"...\\"bao-gia.pdf\\"..."}`` with
    the quotes escaped twice - exactly the box the operator opens to understand why the bot answered badly.
    """
    t = summarize_step(
        RawStep(
            tool_results=[
                ToolResultPart(
                    tool_name="send_file",
                    output={"ok": False, "loi": 'Không có file "bao-gia.pdf" trong kho shared-files'},
                )
            ]
        ),
        500,
        1,
    )
    out = t.tool_results[0]["output"]
    assert '\\"' not in out, f"không được escape ngoặc kép: {out}"
    assert '{"ok"' not in out, f"không được lộ vỏ JSON: {out}"
    assert re.search(r'Không có file "bao-gia\.pdf"', out)


def test_summarize_step_nhanh_hong_cua_tool_hien_cau_object_thuong_khong_bi_nhan_nham_van_ra_json_nhu_cu() -> (
    None
):
    """object thường KHÔNG bị nhận nhầm - vẫn ra JSON như cũ"""
    t = summarize_step(
        RawStep(
            tool_results=[ToolResultPart(tool_name="x", output={"ok": False, "reason": "khác tên trường"})]
        ),
        500,
        1,
    )
    assert re.match(r'^\{"ok"', t.tool_results[0]["output"])


# --- summarizeStep - cờ `hong` cho nhánh hỏng của tool -------------------------------------------------


def test_summarize_step_co_hong_ket_qua_danh_dau_hong_co_hong_true_ket_qua_thuong_thi_khong() -> None:
    """kết quả đánh dấu hỏng có hong:true, kết quả thường thì không

    The UI uses this flag to colour red. The UI must NOT sniff the "LỖI: " prefix in the output: strangers'
    web content goes straight into it so a rule based on words can be composed to match.
    """
    t = summarize_step(
        RawStep(
            tool_results=[
                ToolResultPart(tool_name="web_fetch", output={"ok": False, "loi": "Không đọc được trang"}),
                ToolResultPart(tool_name="get_datetime", output="Bây giờ là 10:00"),
            ]
        ),
        500,
        1,
    )
    assert t.tool_results[0]["hong"] is True
    assert "hong" not in t.tool_results[1], "kết quả thường KHÔNG được gắn cờ"


def test_summarize_step_co_hong_object_co_ok_false_nhung_khac_ten_truong_khong_bi_gan_co() -> None:
    """object có ok:false nhưng khác tên trường KHÔNG bị gắn cờ"""
    t = summarize_step(
        RawStep(
            tool_results=[ToolResultPart(tool_name="x", output={"ok": False, "reason": "khác tên trường"})]
        ),
        500,
        1,
    )
    assert "hong" not in t.tool_results[0]
