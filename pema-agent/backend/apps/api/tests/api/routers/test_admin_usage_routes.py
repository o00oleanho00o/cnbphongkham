# ported from: src/server/routes/overview-routes.test.ts, trace-routes.test.ts, trace-routes-paging.test.ts,
# log-routes.test.ts
"""The usage routes (``/admin/usage/overview``, ``/admin/traces``, ``/admin/logs/app``) over fakes.

Forced differences, all from the contract OpenAPI (changing a route is package G's): the query parameters are
validated by FastAPI, so a junk ``days`` / ``before`` / ``limit`` is a 422 ``validation_failed`` and NOT clamped to
the default or answered with an empty page as the original did. The rules behind the originals still hold: a
broken cursor never falls back to the first page, ``days`` never reaches a scan of the whole table, ``limit`` never
exceeds 50 (traces) or 500 (logs). A malformed LOG cursor (a free string in the contract) still returns an empty
page. Authentication is wired at mount time by package B1 (``provide_clinic_id`` is the seam), so the 401 cases
are not asserted here. Test names are the snake_case form of ``describe_it``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from pema.agent.testing import make_caps
from pema.api import errors as api_errors
from pema.api.routers import admin_usage
from pema.channels.registry import InMemoryChannelRegistry
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.admin_agent import TraceTurnRow
from pema_contracts.conversation import AccountStats, DailyUsage, TraceStepRow
from pema_contracts.testing import (
    FAKE_CLINIC_ID,
    FakeChannel,
    InMemoryAccountStore,
    fake_account_config,
)

NOW = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
SO_LUOT = 12


class FakeUsage:
    def __init__(self) -> None:
        self.daily_calls: list[tuple[str, str, str]] = []

    async def get_daily_usage(
        self, clinic_id: UUID, account_id: str, since_utc_iso: str, time_zone: str
    ) -> list[DailyUsage]:
        self.daily_calls.append((account_id, since_utc_iso, time_zone))
        return [DailyUsage(day="2026-09-20", turns=3, input_tokens=100, output_tokens=40)]

    async def get_account_stats(
        self, clinic_id: UUID, account_id: str, start_of_today_utc: str
    ) -> AccountStats:
        return AccountStats(
            account_id=account_id, threads=2, messages_today=5, turns_today=3, tokens_today=140
        )


class FakeTraces:
    """12 turns, ids 1..12, newest first (id descending); some belong to ``acc/th`` and some to another thread."""

    def __init__(self) -> None:
        self.rows = [
            TraceTurnRow(
                id=i,
                account_id="acc" if i % 4 else "other",
                thread_id="th",
                source="message",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                steps=1,
                created_at=NOW - timedelta(minutes=SO_LUOT - i),
            )
            for i in range(SO_LUOT, 0, -1)
        ]

    async def list_recent_turns(
        self,
        clinic_id: UUID,
        *,
        before: int | None,
        limit: int,
        account_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[TraceTurnRow]:
        rows = [
            r
            for r in self.rows
            if (before is None or r.id < before)
            and (account_id is None or r.account_id == account_id)
            and (thread_id is None or r.thread_id == thread_id)
        ]
        return rows[:limit]

    async def get_turn_steps(self, clinic_id: UUID, turn_id: int) -> list[TraceStepRow]:
        if turn_id != 7:
            return []
        return [
            TraceStepRow(
                id=1,
                turn_id=7,
                created_at=NOW,
                step_number=1,
                reasoning="Cần tra web trước",
                tool_calls=[{"name": "web_search", "input": '{"q":"giá vàng"}'}],
                tool_results=[{"name": "web_search", "output": "3 kết quả"}],
                finish_reason="tool-calls",
                warnings=["unsupported-setting - size"],
            ),
            TraceStepRow(
                id=2,
                turn_id=7,
                created_at=NOW,
                step_number=2,
                text="Giá vàng hôm nay là...",
                finish_reason="stop",
            ),
        ]


def _dong(level: str, scope: str, msg: str, **fields: object) -> str:
    stamp = datetime.now(UTC).isoformat(timespec="milliseconds")
    return json.dumps(
        {"time": stamp, "level": level, "scope": scope, "msg": msg, **fields}, ensure_ascii=False
    )


class Harness:
    def __init__(self, tmp_path: Path, *, log_enabled: bool) -> None:
        self.usage = FakeUsage()
        self.traces = FakeTraces()
        self.accounts = InMemoryAccountStore(
            fake_account_config(id="acc-online", label="Bot A"),
            fake_account_config(id="acc-off", label="Bot B", enabled=False),
        )
        self.channels = InMemoryChannelRegistry()
        self.channels.register(FAKE_CLINIC_ID, FakeChannel(caps=make_caps(), account="acc-online"))
        (tmp_path / "bot.log").write_text(
            "\n".join(
                [
                    _dong("debug", "agent-loop", "chi tiết step"),
                    _dong("info", "message-turn", "xử lý lượt", thread_id="t-9"),
                    _dong("error", "account-manager", "mất kết nối Zalo"),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        app = FastAPI()
        api_errors.install_error_handlers(app)
        for router in (admin_usage.router, admin_usage.traces_router, admin_usage.logs_router):
            app.include_router(router)

        for dependency, value in (
            (admin_usage.provide_clinic_id, FAKE_CLINIC_ID),
            (admin_usage.provide_accounts, self.accounts),
            (admin_usage.provide_usage, self.usage),
            (admin_usage.provide_traces, self.traces),
            (admin_usage.provide_channels, self.channels),
            (admin_usage.provide_log_source, admin_usage.LogSource(tmp_path, log_enabled)),
        ):
            app.dependency_overrides[dependency] = _provider(value)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _provider(value: Any) -> Any:
    async def dependency() -> Any:
        return value

    return dependency


@pytest.fixture
async def h(tmp_path: Path) -> AsyncIterator[Harness]:
    install_tuning_provider(StaticTuningProvider({}))
    harness = Harness(tmp_path, log_enabled=True)
    yield harness
    await harness.client.aclose()
    reset_tuning_provider()


# ------------------------------------------------------------------------------------------------ overview


async def overview(h: Harness, query: str = "") -> httpx.Response:
    return await h.client.get(f"/admin/usage/overview{query}")


async def test_overview_khong_truyen_days_thi_mac_dinh_7(h: Harness) -> None:
    """không truyền days thì mặc định 7"""
    r = await overview(h)
    assert r.status_code == 200
    assert r.json()["days"] == 7


@pytest.mark.parametrize("days", [7, 14, 30])
async def test_overview_nhan_dung_cac_moc_duoc_phep(h: Harness, days: int) -> None:
    """nhận đúng các mốc được phép"""
    assert (await overview(h, f"?days={days}")).json()["days"] == days


@pytest.mark.parametrize("days", ["999", "100000", "0", "-5", "1.5", "abc", "7;DROP TABLE"])
async def test_overview_so_ngoai_danh_sach_bi_tu_choi_khong_quet_toan_bang(h: Harness, days: str) -> None:
    """số ngoài danh sách bị từ chối (422) - chặn quét toàn bảng usage; không bao giờ đi tiếp với giá trị lạ"""
    r = await overview(h, f"?days={days}")
    assert r.status_code == 422
    assert h.usage.daily_calls == []


async def test_overview_accounts_online_state_usage_and_the_bot_clock(h: Harness) -> None:
    """account (DB + trạng thái online) + usage; mốc hôm nay theo BOT_TIMEZONE"""
    body = (await overview(h, "?days=14")).json()
    assert [(a["id"], a["enabled"], a["online"]) for a in body["accounts"]] == [
        ("acc-online", True, True),
        ("acc-off", False, False),
    ]
    assert [u["account_id"] for u in body["usage_by_account"]] == ["acc-online", "acc-off"]
    assert body["usage_by_account"][0]["daily"][0]["turns"] == 3
    assert body["stats_by_account"][0]["tokens_today"] == 140
    assert body["timezone"] == "Asia/Ho_Chi_Minh"
    assert len(body["today_key"]) == 10
    assert body["system"]["version"]
    # one call per account, in the bot's zone, the window starting at a local day boundary (17:00Z in Vietnam)
    assert {zone for _a, _s, zone in h.usage.daily_calls} == {"Asia/Ho_Chi_Minh"}
    assert all(since.endswith("T17:00:00.000Z") for _a, since, _z in h.usage.daily_calls)


# -------------------------------------------------------------------------------------------------- traces


async def lat_het_trang(h: Harness, path: str, limit: int) -> list[int]:
    out: list[int] = []
    cursor: int | None = None
    for _round in range(50):
        query = f"?limit={limit}" + ("" if cursor is None else f"&before={cursor}")
        body = (await h.client.get(f"/admin/traces{path}{query}")).json()
        out.extend(t["id"] for t in body["turns"])
        if body["next_cursor"] is None:
            return out
        cursor = body["next_cursor"]
    raise AssertionError("lật quá 50 trang - con trỏ không tiến")


@pytest.mark.parametrize("path", ["", "/acc/th"])
async def test_phan_trang_trace_lat_tung_trang_ra_dung_danh_sach_doc_mot_lan(h: Harness, path: str) -> None:
    """lật từng trang ra đúng danh sách đọc một lần"""
    one_go = [t["id"] for t in (await h.client.get(f"/admin/traces{path}?limit=50")).json()["turns"]]
    assert len(one_go) == (SO_LUOT if path == "" else 9)
    for limit in (1, 3, 5, 11, 12):
        assert await lat_het_trang(h, path, limit) == one_go, f"cỡ trang {limit}"


@pytest.mark.parametrize("path", ["", "/acc/th"])
async def test_phan_trang_trace_moi_nhat_truoc_next_cursor_null_o_trang_cuoi(h: Harness, path: str) -> None:
    """mới nhất trước, nextCursor null ở trang cuối"""
    page = (await h.client.get(f"/admin/traces{path}?limit=50")).json()
    ids = [t["id"] for t in page["turns"]]
    assert ids == sorted(ids, reverse=True), "phải giảm dần theo id"
    assert page["next_cursor"] is None
    half = (await h.client.get(f"/admin/traces{path}?limit=5")).json()
    assert len(half["turns"]) == 5
    assert half["next_cursor"] == half["turns"][4]["id"], "con trỏ phải là id lượt CUỐI trang"


async def test_phan_trang_trace_trang_vua_khit_thi_next_cursor_phai_null(h: Harness) -> None:
    """trang VỪA KHÍT số lượt còn lại thì nextCursor phải null

    The easy miss: ask for exactly the number of turns that exist. Mistaking ``>`` for ``>=`` in the "is there
    more" check leaves the "Xem thêm" button on, and pressing it gives an empty page.
    """
    exact = (await h.client.get(f"/admin/traces?limit={SO_LUOT}")).json()
    assert len(exact["turns"]) == SO_LUOT
    assert exact["next_cursor"] is None, "vừa hết mà vẫn báo còn"
    # the contract caps the page at 50 so check the "exactly the rest" case on the last two as well
    page = (await h.client.get(f"/admin/traces?limit={SO_LUOT - 2}")).json()
    assert page["next_cursor"] is not None
    last = (await h.client.get(f"/admin/traces?limit=2&before={page['next_cursor']}")).json()
    assert len(last["turns"]) == 2
    assert last["next_cursor"] is None, "hai lượt cuối mà vẫn báo còn"


@pytest.mark.parametrize("junk", ["abc", "0", "-5", "1.5", "9e99"])
async def test_phan_trang_trace_con_tro_hong_bi_tu_choi_khong_roi_ve_trang_dau(h: Harness, junk: str) -> None:
    """con trỏ hỏng -> 422, KHÔNG rơi về trang đầu

    The original answered an empty page; the contract validates ``before`` (``ge=1``), which satisfies the same
    rule: falling back to the first page is how a client appends endless copies without anyone noticing.
    """
    r = await h.client.get(f"/admin/traces?before={junk}")
    assert r.status_code == 422
    assert "turns" not in r.json()


async def test_phan_trang_trace_con_tro_tro_ra_ngoai_pham_vi_thi_tra_rong_khong_loi(h: Harness) -> None:
    """con trỏ trỏ ra ngoài phạm vi thì trả rỗng, không lỗi"""
    r = await h.client.get("/admin/traces?before=1")
    assert r.status_code == 200
    assert r.json() == {"turns": [], "next_cursor": None}


async def test_phan_trang_trace_tran_50_luot_van_giu_du_client_xin_nhieu_hon(h: Harness) -> None:
    """trần 50 lượt vẫn giữ dù client xin nhiều hơn (422, không bao giờ trả quá 50)"""
    assert (await h.client.get("/admin/traces?limit=99999")).status_code == 422


async def test_traces_doc_trace_chi_tiet_mot_luot_co_tool_call_warnings_reasoning(h: Harness) -> None:
    """đọc trace chi tiết 1 lượt - có tool call, warnings, reasoning"""
    r = await h.client.get("/admin/traces/turn/7")
    assert r.status_code == 200
    steps = r.json()
    assert len(steps) == 2
    assert steps[0]["reasoning"] == "Cần tra web trước"
    assert steps[0]["tool_calls"][0]["name"] == "web_search"
    assert steps[0]["warnings"] == ["unsupported-setting - size"]


async def test_traces_turn_id_khong_ton_tai_tra_mang_rong_khong_phai_500(h: Harness) -> None:
    """turn id không tồn tại trả mảng rỗng, không phải 500"""
    r = await h.client.get("/admin/traces/turn/999999")
    assert r.status_code == 200
    assert r.json() == []


async def test_traces_turn_id_khong_phai_so_duong_bi_chan_truoc_khi_dung_db(h: Harness) -> None:
    """turn id không phải số nguyên dương -> 422, không đụng DB"""
    assert (await h.client.get("/admin/traces/turn/abc")).status_code == 422
    assert (await h.client.get("/admin/traces/turn/0")).status_code == 422


# ---------------------------------------------------------------------------------------------------- logs


async def read_logs(h: Harness, query: str = "") -> dict[str, Any]:
    r = await h.client.get(f"/admin/logs/app{query}")
    assert r.status_code == 200
    return r.json()


async def test_logs_doc_duoc_log_moi_nhat_dung_dau_kem_truong_phu(h: Harness) -> None:
    """đọc được log, MỚI NHẤT đứng đầu, kèm trường phụ"""
    body = await read_logs(h)
    assert body["disabled"] is False
    assert body["entries"][0]["message"] == "mất kết nối Zalo", "dòng cuối của file mới nhất đứng đầu"
    assert body["entries"][1]["fields"]["thread_id"] == "t-9", "trường phụ là chỗ chứa ngữ cảnh"
    assert body["entries"][0]["level"] == "error"


async def test_logs_loc_theo_muc_warn_tro_len_bo_het_info_va_debug(h: Harness) -> None:
    """lọc theo mức: warn trở lên bỏ hết info và debug"""
    body = await read_logs(h, "?level=warn")
    assert body["entries"][0]["scope"] == "account-manager"
    assert not any(e["scope"] == "agent-loop" for e in body["entries"]), "debug phải bị loại"


async def test_logs_loc_theo_scope(h: Harness) -> None:
    """lọc theo scope"""
    body = await read_logs(h, "?scope=agent-loop")
    assert [e["message"] for e in body["entries"]] == ["chi tiết step"]


async def test_logs_tim_theo_chu(h: Harness) -> None:
    """tìm theo chữ"""
    assert len((await read_logs(h, "?search=kết%20nối"))["entries"]) == 1


async def test_logs_tra_danh_sach_scope_de_dashboard_dung_o_loc(h: Harness) -> None:
    """trả danh sách scope để dashboard dựng ô lọc"""
    body = await read_logs(h)
    for scope in ("account-manager", "agent-loop", "message-turn"):
        assert scope in body["scopes"], f"thiếu scope {scope}"
    assert body["scopes"] == sorted(body["scopes"]), "scope phải sắp xếp"


async def test_logs_limit_bi_kep_tran_xin_99999_khong_keo_sap_trang(h: Harness) -> None:
    """limit bị kẹp trần: xin 99999 bị từ chối (tối đa 500)"""
    assert (await h.client.get("/admin/logs/app?limit=99999")).status_code == 422
    assert len((await read_logs(h, "?limit=500"))["entries"]) <= 500


async def test_logs_con_tro_hong_tra_trang_rong_khong_roi_ve_trang_dau(h: Harness) -> None:
    """con trỏ log hỏng -> trang RỖNG, không phải trang đầu"""
    body = await read_logs(h, "?before=abc")
    assert body["entries"] == []
    assert body["next_cursor"] is None


async def test_logs_paging_with_a_cursor_returns_the_rest_without_repeats(h: Harness) -> None:
    """con trỏ hợp lệ lật trang đủ, không lặp"""
    first = await read_logs(h, "?limit=2")
    assert len(first["entries"]) == 2
    assert first["next_cursor"]
    rest = await read_logs(h, f"?limit=2&before={first['next_cursor']}")
    seen = [e["message"] for e in first["entries"]] + [e["message"] for e in rest["entries"]]
    assert sorted(seen) == sorted(["chi tiết step", "xử lý lượt", "mất kết nối Zalo"])
    assert rest["next_cursor"] is None


async def test_logs_file_logging_off_says_so_instead_of_an_empty_page(tmp_path: Path) -> None:
    """ghi log ra file đang tắt thì nói rõ, không trả trang rỗng im lặng"""
    harness = Harness(tmp_path, log_enabled=False)
    try:
        body = (await harness.client.get("/admin/logs/app")).json()
    finally:
        await harness.client.aclose()
    assert body["disabled"] is True
    assert body["entries"] == []
    assert body["hint"]
