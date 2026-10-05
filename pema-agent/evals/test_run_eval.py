# ported from: none (tests of the Python runner: the original ``run-eval.ts`` is only ever run by hand)
"""The eval runner end to end against a FAKE model: no network, no key.

This is the test that the runner measures what it says it measures: the case set goes through
``run_agent_turn`` for real (prompt building, tool filtering, the loop, the trace), and only the model is
scripted. What it proves:

* a turn that behaves is scored PASS and one that does not is scored FAIL;
* a dead provider is a FAIL, never a green "no tool called" (the false green of the first real run);
* the seeds of a case (persona, disabled tools, history, remembered facts) really reach the model;
* every reply goes through the FAKE Zalo API and nothing else;
* the formatting cases are scored FAILED, not skipped, when no formatter is wired.

For a run against a real model see ``evals/README.md`` (Ollama on the GPU PC); that run was NOT made here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from evals.eval_case_type import EvalCase
from evals.eval_cases import EVAL_CASES
from evals.eval_formatting_view import SentMessage, ZaloStyle
from evals.run_eval import EvalWiring, main, run_cases, select_cases
from pema.agent.agent_loop import ROUTER_DOWN_REPLY
from pema.agent.model_types import ModelCompletion, ModelRequest
from pema.agent.providers.errors import ProviderCallError
from pema.agent.streaming_model_test_helper import goi_tool, prompt_text, tool_keys, tra_loi
from pema.agent.testing_engine import no_sleep
from pema.config import env as env_module
from pema.config.env_llm import get_llm_env

Answer = Callable[[ModelRequest], ModelCompletion | Exception]


class CaseModel:
    """A fake ``ChatModel`` that answers by what the request says; records every request."""

    def __init__(self, answer: Answer) -> None:
        self._answer = answer
        self.calls: list[ModelRequest] = []

    @property
    def model_id(self) -> str:
        return "fake-eval-model"

    async def complete(self, request: ModelRequest) -> ModelCompletion:
        self.calls.append(request)
        outcome = self._answer(request)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _has_tool_result(request: ModelRequest) -> bool:
    return any(m.get("role") == "tool" for m in request.messages)


def _last_user_text(request: ModelRequest) -> str:
    users = [m for m in request.messages if m.get("role") == "user"]
    return json.dumps(users[-1].get("content"), ensure_ascii=False) if users else ""


def good_answer(request: ModelRequest) -> ModelCompletion | Exception:
    if "mấy giờ" in _last_user_text(request) and not _has_tool_result(request):
        return goi_tool("get_datetime")
    if "mấy giờ" in _last_user_text(request):
        return tra_loi("Bây giờ là 9 giờ sáng ạ.")
    return tra_loi("Chào bạn, mình giúp được gì cho bạn nào?")


def wiring(model: CaseModel, **patch: object) -> EvalWiring:
    def resolve(*_args: object) -> CaseModel:
        return model

    return EvalWiring(resolve_model=resolve, sleep=no_sleep, retry_initial_delay_s=0.0, **patch)  # type: ignore[arg-type]


def by_name(*names: str) -> list[EvalCase]:
    return select_cases(",".join(names), EVAL_CASES)


async def test_run_cases_turn_dung_hanh_vi_thi_dat_va_moi_tin_di_qua_api_gia() -> None:
    """a well-behaved model passes both cases and the reply went through the fake Zalo API only"""
    model = CaseModel(good_answer)
    lines: list[str] = []
    out = await run_cases(by_name("gio-chinh-xac", "khong-tra-thua"), wiring(model), lines.append)

    assert [r.dat for r in out.ket_qua] == [True, True], [r.ly_do_hong for r in out.ket_qua]
    assert out.ket_qua[0].tool_da_goi == ["get_datetime"]
    assert out.ket_qua[1].tool_da_goi == []
    assert all(r.tokens > 0 for r in out.ket_qua)
    # one reply per case, each recorded as ONE call of the fake API
    assert out.tong_loi_goi_api == 2
    assert lines == ["Đang chạy gio-chinh-xac... ĐẠT", "Đang chạy khong-tra-thua... ĐẠT"]


async def test_run_cases_model_khong_goi_tool_can_thiet_thi_hong_voi_ly_do_ro() -> None:
    """a model that guesses the time instead of calling ``get_datetime`` is scored FAILED, with the reason"""
    model = CaseModel(lambda _r: tra_loi("Chắc khoảng 3 giờ chiều."))
    out = await run_cases(by_name("gio-chinh-xac"), wiring(model))

    assert out.ket_qua[0].dat is False
    assert 'Phải gọi "get_datetime"' in out.ket_qua[0].ly_do_hong[0]
    assert out.ket_qua[0].tokens > 0, "the turn did run: a refusal to use the tool, not a dead turn"


async def test_run_cases_provider_chet_thi_hong_khong_phai_khong_goi_tool_nao_nen_dat() -> None:
    """a dead provider is FAILED even for a ``khong_goi_tool`` case (the false green of the first real run)"""
    model = CaseModel(lambda _r: ProviderCallError("Upstream unavailable", status_code=503))
    out = await run_cases(by_name("khong-tra-thua", "cong-cu-hep"), wiring(model))

    assert [r.dat for r in out.ket_qua] == [False, False]
    assert "Lượt agent ném lỗi" in out.ket_qua[0].ly_do_hong[0]
    assert all(r.tokens == 0 for r in out.ket_qua)
    assert out.tong_loi_goi_api == 0, "a failed turn sends nothing"


async def test_run_cases_cau_bao_loi_he_thong_voi_token_khac_0_van_hong() -> None:
    """a model that answers the system error sentence with real tokens is FAILED (``phat_hien_luot_hong``)"""
    model = CaseModel(lambda _r: tra_loi(ROUTER_DOWN_REPLY))
    out = await run_cases(by_name("khong-tra-thua"), wiring(model))

    assert out.ket_qua[0].dat is False
    assert out.ket_qua[0].tokens > 0
    assert "câu báo lỗi hệ thống" in out.ket_qua[0].ly_do_hong[0]


async def test_run_cases_tool_bi_tat_khong_duoc_dua_cho_model() -> None:
    """``disabled_tools`` of a case turns the tool off in the schema the model receives"""
    model = CaseModel(good_answer)
    await run_cases(by_name("gio-chinh-xac"), wiring(model))

    offered = tool_keys(model.calls[0])
    assert "get_datetime" in offered
    for tat in ("create_image", "create_word_document", "create_excel_file"):
        assert tat not in offered


async def test_run_cases_persona_rieng_cua_case_toi_duoc_system_prompt() -> None:
    """the real-style persona of a case is in the system prompt of the call"""
    model = CaseModel(lambda _r: tra_loi("1. Một\n2. Hai 🙂"))
    await run_cases(by_name("luat-thang-lich-su-cu"), wiring(model))

    assert "Minh Triết, trợ lý Zalo thông minh" in model.calls[0].system


async def test_run_cases_lich_su_dung_san_toi_duoc_model_va_tin_hien_tai_khong_bi_nhan_doi() -> None:
    """the pre-built history reaches the model, and the current message is not duplicated by the history"""
    model = CaseModel(lambda _r: tra_loi("1. Một\n2. Hai 🙂"))
    out = await run_cases(by_name("luat-thang-lich-su-cu"), wiring(model))

    prompt = prompt_text(model.calls[0])
    assert "Minh Triết có thể hỗ trợ anh" in prompt, "the old flat reply is the seeded history"
    # the history already holds one "bạn làm được gì?" of its own; the turn adds the current one exactly once
    assert prompt.count("bạn làm được gì?") == 2
    assert out.ket_qua[0].dat is True, out.ket_qua[0].ly_do_hong


async def test_run_cases_fact_co_san_toi_duoc_model_va_dinh_chinh_thi_sua_dat() -> None:
    """the seeded fact is in the prompt and the correction case passes when the model uses action ``sua``"""

    def answer(request: ModelRequest) -> ModelCompletion | Exception:
        if _has_tool_result(request):
            return tra_loi("Mình đã cập nhật nơi ở của bạn rồi nhé.")
        return goi_tool("save_memory", {"action": "sua", "noi_dung": "Người dùng sống ở Hà Nội"})

    model = CaseModel(answer)
    out = await run_cases(by_name("dinh-chinh-thi-sua"), wiring(model))

    assert "Thành phố Hồ Chí Minh" in prompt_text(model.calls[0])
    assert out.ket_qua[0].dat is True, out.ket_qua[0].ly_do_hong


async def test_run_cases_dinh_chinh_ma_dung_action_them_thi_hong() -> None:
    """calling the right tool with the WRONG action is the bug the case exists to catch"""

    def answer(request: ModelRequest) -> ModelCompletion | Exception:
        if _has_tool_result(request):
            return tra_loi("Mình đã ghi nhớ rồi nhé.")
        return goi_tool("save_memory", {"action": "them", "noi_dung": "Người dùng sống ở Hà Nội"})

    out = await run_cases(by_name("dinh-chinh-thi-sua"), wiring(CaseModel(answer)))

    assert out.ket_qua[0].dat is False
    assert "Tham số" in " ".join(out.ket_qua[0].ly_do_hong)


async def test_run_cases_case_dinh_dang_khong_co_formatter_thi_hong_khong_bo_qua() -> None:
    """a formatting case without a wired formatter is FAILED with "not provided", never skipped"""
    model = CaseModel(lambda _r: tra_loi("Chào bạn, mình khỏe, cảm ơn bạn!"))
    out = await run_cases(by_name("tro-chuyen-thi-dung-trang-tri"), wiring(model))

    assert out.ket_qua[0].dat is False
    assert "không cung cấp" in " ".join(out.ket_qua[0].ly_do_hong)


async def test_run_cases_case_dinh_dang_co_formatter_thi_do_dung_thu_nguoi_dung_nhan() -> None:
    """with a formatter the styles are measured: plain chat passes, a decorated one fails"""

    def plain(text: str) -> list[SentMessage]:
        return [SentMessage(msg=text)]

    def decorated(text: str) -> list[SentMessage]:
        return [
            SentMessage(
                msg=text,
                styles=[ZaloStyle(start=0, len=4, st="f_18"), ZaloStyle(start=5, len=3, st="c_f27806")],
            )
        ]

    model = CaseModel(lambda _r: tra_loi("Chào bạn, mình khỏe, cảm ơn bạn!"))
    ok = await run_cases(by_name("tro-chuyen-thi-dung-trang-tri"), wiring(model, format_reply=plain))
    bad = await run_cases(by_name("tro-chuyen-thi-dung-trang-tri"), wiring(model, format_reply=decorated))

    assert ok.ket_qua[0].dat is True, ok.ket_qua[0].ly_do_hong
    assert bad.ket_qua[0].dat is False
    assert "Định dạng không đạt" in " ".join(bad.ket_qua[0].ly_do_hong)


async def test_run_cases_tin_tuc_phai_mo_bai_dung_du_lieu_mau_va_dem_so_lan_web_fetch() -> None:
    """the canned web tools give the model something to open: two ``web_fetch`` calls pass the case"""
    state = {"fetched": 0}

    def answer(request: ModelRequest) -> ModelCompletion | Exception:
        if not _has_tool_result(request):
            return goi_tool("web_search", {"query": "tin kinh tế"})
        if state["fetched"] < 2:
            state["fetched"] += 1
            return goi_tool(
                "web_fetch",
                {
                    "url": f"https://news-{state['fetched']}.example.test/thi-truong-"
                    + "ab"[state["fetched"] - 1]
                },
                call_id=f"c{state['fetched']}",
            )
        return tra_loi("Tóm tắt xong ạ.")

    out = await run_cases(by_name("tin-tuc-phai-mo-bai"), wiring(CaseModel(answer)))

    assert out.ket_qua[0].dat is True, out.ket_qua[0].ly_do_hong
    assert out.ket_qua[0].tool_da_goi.count("web_fetch") == 2


def test_select_cases_loc_theo_ten_va_khong_loc_khi_rong() -> None:
    """``EVAL_ONLY``: a comma list filters, empty keeps everything, unknown names keep nothing"""
    assert [c.ten for c in select_cases("tra-cuu, khong-tra-thua", EVAL_CASES)] == [
        "tra-cuu",
        "khong-tra-thua",
    ]
    assert len(select_cases("", EVAL_CASES)) == 17
    assert select_cases("khong-co-case-nay", EVAL_CASES) == []


async def test_main_chay_het_bo_case_thi_in_bang_va_tra_ma_0_khi_dat_het(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main`` with two cases that pass: prints the table and the proof line, exits 0"""
    monkeypatch.setenv("EVAL_ONLY", "gio-chinh-xac,khong-tra-thua")
    lines: list[str] = []
    code = await main(wiring(CaseModel(good_answer)), lines.append)

    assert code == 0
    text = "\n".join(lines)
    assert "2/2 đạt" in text
    assert "2 lời gọi Zalo, tất cả vào API giả - không tin nào ra Zalo thật." in text


async def test_main_co_case_hong_thi_tra_ma_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main`` exits 1 when a case fails and prints the failed case with the bot's reply"""
    monkeypatch.setenv("EVAL_ONLY", "gio-chinh-xac")
    lines: list[str] = []
    code = await main(wiring(CaseModel(lambda _r: tra_loi("Chắc khoảng 3 giờ."))), lines.append)

    assert code == 1
    text = "\n".join(lines)
    assert "HỎNG: gio-chinh-xac" in text
    assert "Bot trả lời" in text


async def test_main_eval_only_khong_khop_case_nao_thi_dung_va_liet_ke_ten_co(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main`` stops with the list of valid names when ``EVAL_ONLY`` matches nothing"""
    monkeypatch.setenv("EVAL_ONLY", "khong-co")
    lines: list[str] = []
    code = await main(wiring(CaseModel(good_answer)), lines.append)

    assert code == 1
    assert "gio-chinh-xac" in "\n".join(lines)


async def test_main_thieu_api_key_thi_dung_han_khong_chay_nua_vo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """with no key anywhere ``main`` STOPS (exit 1) instead of running every case red for a network error"""
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "PEMA_EVAL_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()
    lines: list[str] = []
    try:
        code = await main(EvalWiring(), lines.append)
    finally:
        get_llm_env.cache_clear()

    assert code == 1
    assert "Thiếu API key" in "\n".join(lines)
