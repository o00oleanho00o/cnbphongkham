# ported from: src/agent/tools/schedule-task-tool.test.ts
"""Tests of the ``schedule_task`` tool.

Forced deviations: the real SQLite store of the original becomes the in-memory ``FakeScheduler`` of
``pema.agent.tools.testing`` behind ``SchedulerPort``; the schedule parser (package S) is replaced by a small
time-zone-aware fake below, because the conversion date+time -> UTC belongs to the parser, not to the
tool; the
original ran the first test under two process time zones (``process.env.TZ``), which has no meaning for
``zoneinfo``, so it runs once under ``BOT_TIMEZONE``. ``inputSchema.safeParse`` becomes
``tool.input_model.model_validate`` and ``asSchema(...).jsonSchema`` becomes ``tool.parameters``.

Added for the clinic (not in the original): the ``PolicyHooks.check_job`` tests at the end.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from pema.agent.tools.schedule_task_tool import create_schedule_task_tool
from pema.agent.tools.testing import (
    FakeScheduleParser,
    FakeScheduler,
    make_tool_context,
    make_tool_deps,
)
from pema.agent.tools.tool_deps import ParseScheduleResult, ToolDeps
from pema.agent.tools.tool_failure_result_test_helper import ket_qua_thanh_cong, loi_cua_tool
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.channel import ChannelKind, ThreadKind
from pema_contracts.policy import JobAction, JobDecision, PermissivePolicyHooks, PolicyContext
from pema_contracts.scheduler import (
    CreateScheduledJobInput,
    OnceAtInput,
    OnceInMinutesInput,
    OnceSchedule,
    ScheduledJob,
    ScheduleInput,
)
from pema_contracts.testing import make_inbound
from pema_contracts.tools import ToolContext

ACCOUNT_ID = "acc-test"
BOT_TZ = "Asia/Ho_Chi_Minh"

# The "once" moment must ALWAYS be in the FUTURE relative to the real run time (the parser rejects a past
# moment) - +7 days is far enough not to "expire" by itself, unlike the old hardcoded "2026-08-01" that fell
# into the past on that very day and turned the test red for good the day after.
_ONCE_MOMENT = (datetime.now(ZoneInfo(BOT_TZ)) + timedelta(days=7)).replace(minute=0, second=0, microsecond=0)
ONCE_TEST_DATE = _ONCE_MOMENT.strftime("%Y-%m-%d")
ONCE_TEST_TIME = _ONCE_MOMENT.strftime("%H:%M")
ONCE_TEST_DATE_VN = _ONCE_MOMENT.strftime("%d/%m/%Y")
ONCE_TEST_RUN_AT_UTC = _ONCE_MOMENT.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class TzParser:
    """Stands for ``parse_schedule`` of package S: date+time in the given zone -> UTC, rejects the past; the
    ``every`` / ``cron`` cases are delegated to ``FakeScheduleParser``."""

    def __init__(self) -> None:
        self._base = FakeScheduleParser()

    def parse_schedule(
        self, schedule: ScheduleInput, *, time_zone: str, min_interval_minutes: int
    ) -> ParseScheduleResult:
        moment: datetime | None = None
        if isinstance(schedule, OnceAtInput):
            local = datetime.strptime(f"{schedule.date} {schedule.time}", "%Y-%m-%d %H:%M")
            moment = local.replace(tzinfo=ZoneInfo(time_zone)).astimezone(UTC)
        elif isinstance(schedule, OnceInMinutesInput):
            moment = datetime.now(UTC) + timedelta(minutes=schedule.in_minutes)
        if moment is None:
            return self._base.parse_schedule(
                schedule, time_zone=time_zone, min_interval_minutes=min_interval_minutes
            )
        if moment <= datetime.now(UTC):
            return ParseScheduleResult(
                ok=False, error="Mốc giờ này đã ở quá khứ, hãy chọn một mốc giờ sau bây giờ."
            )
        return ParseScheduleResult(
            ok=True, schedule=OnceSchedule(run_at_utc=moment.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        )


@pytest.fixture(autouse=True)
def _reset_tuning() -> Iterator[None]:
    yield
    reset_tuning_provider()


@pytest.fixture
def deps() -> ToolDeps:
    return make_tool_deps(schedule_parser=TzParser())


def make_ctx(
    thread_id: str = "t-1",
    sender_id: str = "u-1",
    account_patch: dict[str, object] | None = None,
    isolated: bool = False,
) -> ToolContext:
    message = make_inbound(
        "",
        channel=ChannelKind.ZALO_PERSONAL,
        account_id=ACCOUNT_ID,
        thread_id=thread_id,
        sender_id=sender_id,
        thread_kind=ThreadKind.GROUP,
        is_group=True,
        mentions_me=True,
    )
    return make_tool_context(message=message, account_patch=account_patch, isolated=isolated)


async def run(ctx: ToolContext, deps: ToolDeps, args: dict[str, Any]) -> object:
    return await create_schedule_task_tool(ctx, deps).execute(args)


def scheduler_of(deps: ToolDeps) -> FakeScheduler:
    assert isinstance(deps.scheduler, FakeScheduler)
    return deps.scheduler


async def jobs_of(deps: ToolDeps, thread_id: str) -> list[ScheduledJob]:
    return await deps.scheduler.list_jobs_for_thread(make_ctx().clinic_id, ACCOUNT_ID, thread_id)


def every(minutes: int) -> dict[str, Any]:
    return {"kind": "every", "minutes": minutes}


def create_args(name: str, minutes: int = 30, kind: str = "message", payload: str = "p") -> dict[str, Any]:
    return {"action": "create", "name": name, "kind": kind, "payload": payload, "schedule": every(minutes)}


# ------------------------------------------------------------------------------ action create


async def test_schedule_task_action_create_once_date_time_quy_doi_dung_utc(deps: ToolDeps) -> None:
    """once date+time quy đổi đúng UTC (BOT_TIMEZONE mặc định Asia/Ho_Chi_Minh), không phụ thuộc TZ tiến
    trình"""
    ctx = make_ctx("t-once")
    result = await run(
        ctx,
        deps,
        {
            "action": "create",
            "name": "Nhắc họp",
            "kind": "message",
            "payload": "Họp với anh Nam",
            "schedule": {"kind": "once", "date": ONCE_TEST_DATE, "time": ONCE_TEST_TIME},
        },
    )

    [job] = await jobs_of(deps, "t-once")
    assert job.run_at == ONCE_TEST_RUN_AT_UTC
    assert isinstance(result, str)
    # must read back the exact moment for the user to confirm
    assert f"{ONCE_TEST_TIME} ngày {ONCE_TEST_DATE_VN}" in result


async def test_schedule_task_action_create_kind_agent_luu_dung_payload_la_prompt(deps: ToolDeps) -> None:
    """kind='agent' lưu đúng payload là prompt, trả về id để list/cancel sau này dùng"""
    ctx = make_ctx("t-agent")
    result = await run(
        ctx,
        deps,
        {
            "action": "create",
            "name": "Báo cáo sáng",
            "kind": "agent",
            "payload": "Tóm tắt tin công nghệ nổi bật hôm nay",
            "schedule": every(60),
        },
    )

    [job] = await jobs_of(deps, "t-agent")
    assert job.kind == "agent"
    assert job.payload == "Tóm tắt tin công nghệ nổi bật hôm nay"
    assert isinstance(result, str)
    assert re.search(re.escape(job.id), result)


async def test_schedule_task_action_create_job_ghim_cung_vao_account_thread_cua_nguoi_tao(
    deps: ToolDeps,
) -> None:
    """job ghim cứng vào (accountId, threadId) của người tạo - không có tham số đích khác"""
    ctx = make_ctx("t-pin", "u-pin")
    await run(ctx, deps, create_args("x", 30, "message", "y"))

    [job] = await jobs_of(deps, "t-pin")
    assert job.account_id == ACCOUNT_ID
    assert job.thread_id == "t-pin"
    assert job.created_by == "u-pin"


async def test_schedule_task_action_create_nguoi_ngoai_allowlist_bi_tu_choi_tao_lich(deps: ToolDeps) -> None:
    """người NGOÀI allowlist bị từ chối tạo lịch - job không được lưu"""
    ctx = make_ctx(
        "t-allowlist-tu-choi",
        "u-la",
        account_patch={"allowlist": {"mode": "list", "user_ids": ["u-duoc-phep"]}},
    )

    result = await run(ctx, deps, create_args("x", 30, "message", "y"))

    assert re.search(r"allowlist|danh sách được phép", loi_cua_tool(result), re.IGNORECASE)
    assert len(await jobs_of(deps, "t-allowlist-tu-choi")) == 0, "không được tạo job nào"


async def test_schedule_task_action_create_nguoi_trong_allowlist_tao_duoc_lich_binh_thuong(
    deps: ToolDeps,
) -> None:
    """người TRONG allowlist tạo được lịch bình thường"""
    ctx = make_ctx(
        "t-allowlist-ok",
        "u-duoc-phep",
        account_patch={"allowlist": {"mode": "list", "user_ids": ["u-duoc-phep"]}},
    )

    await run(ctx, deps, create_args("x", 30, "message", "y"))

    assert len(await jobs_of(deps, "t-allowlist-ok")) == 1


async def test_schedule_task_action_create_cham_tran_scheduler_max_jobs_per_thread_thi_bi_tu_choi(
    deps: ToolDeps,
) -> None:
    """chạm trần SCHEDULER_MAX_JOBS_PER_THREAD job đang bật thì bị từ chối"""
    install_tuning_provider(StaticTuningProvider({"SCHEDULER_MAX_JOBS_PER_THREAD": 2}))
    ctx = make_ctx("t-cap")

    await run(ctx, deps, create_args("job 1"))
    await run(ctx, deps, create_args("job 2"))
    ket_qua = await run(ctx, deps, create_args("job 3 - phải bị chặn"))

    assert re.search(r"trần|chạm|đủ 2", loi_cua_tool(ket_qua), re.IGNORECASE)
    assert len(await jobs_of(deps, "t-cap")) == 2, "job thứ 3 không được lưu"


async def test_schedule_task_action_create_job_da_tat_khong_tinh_vao_tran(deps: ToolDeps) -> None:
    """job đã TẮT không tính vào trần - hủy bớt rồi vẫn tạo lại được"""
    install_tuning_provider(StaticTuningProvider({"SCHEDULER_MAX_JOBS_PER_THREAD": 1}))
    ctx = make_ctx("t-cap-tat")
    await run(ctx, deps, create_args("job 1"))
    [job1] = await jobs_of(deps, "t-cap-tat")
    await deps.scheduler.set_enabled(ctx.clinic_id, ACCOUNT_ID, "t-cap-tat", job1.id, False)

    ket_qua = await run(ctx, deps, create_args("job 2"))

    # job đã tắt không được tính vào trần
    assert not re.search(r"trần|chạm", str(ket_qua), re.IGNORECASE)


async def test_schedule_task_action_create_lich_khong_hop_le_every_qua_day_tra_cau_loi_khong_throw(
    deps: ToolDeps,
) -> None:
    """lịch không hợp lệ (every quá dày) trả câu lỗi có chữ, KHÔNG throw, không lưu job"""
    ctx = make_ctx("t-invalid-every")
    result = await run(ctx, deps, create_args("x", 1, "message", "y"))

    assert re.search(r"tối thiểu|spam", loi_cua_tool(result), re.IGNORECASE)
    assert len(await jobs_of(deps, "t-invalid-every")) == 0


async def test_schedule_task_action_create_lich_once_o_qua_khu_tra_cau_loi_khong_luu_job(
    deps: ToolDeps,
) -> None:
    """lịch once đã ở quá khứ trả câu lỗi có chữ, không lưu job"""
    ctx = make_ctx("t-invalid-past")
    result = await run(
        ctx,
        deps,
        {
            "action": "create",
            "name": "x",
            "kind": "message",
            "payload": "y",
            "schedule": {"kind": "once", "date": "2020-01-01", "time": "08:00"},
        },
    )

    assert "quá khứ" in loi_cua_tool(result)
    assert len(await jobs_of(deps, "t-invalid-past")) == 0


# ------------------------------------------------------------------------------ action list


async def test_schedule_task_action_list_chi_liet_ke_job_cua_dung_thread(deps: ToolDeps) -> None:
    """chỉ liệt kê job của đúng thread, không lẫn thread khác"""
    ctx_a = make_ctx("t-list-a")
    ctx_b = make_ctx("t-list-b")
    await run(ctx_a, deps, create_args("A1"))
    await run(ctx_b, deps, create_args("B1"))

    result = await run(ctx_a, deps, {"action": "list"})

    assert isinstance(result, str)
    assert "A1" in result
    assert "B1" not in result, "không được thấy job của thread khác"


async def test_schedule_task_action_list_thread_chua_co_job_nao_thi_tra_cau_ro_rang(deps: ToolDeps) -> None:
    """thread chưa có job nào thì trả câu rõ ràng, không phải chuỗi rỗng"""
    result = await run(make_ctx("t-list-rong"), deps, {"action": "list"})
    assert isinstance(result, str)
    assert re.search(r"chưa có lịch", result, re.IGNORECASE)


# ------------------------------------------------------------------------------ action cancel


async def test_schedule_task_action_cancel_huy_dung_job_cua_thread_minh(deps: ToolDeps) -> None:
    """hủy đúng job của thread mình - job biến mất khỏi list"""
    ctx = make_ctx("t-cancel-ok")
    await run(ctx, deps, create_args("x"))
    [job] = await jobs_of(deps, "t-cancel-ok")

    result = await run(ctx, deps, {"action": "cancel", "id": job.id})

    assert isinstance(result, str)
    assert "Đã hủy" in result
    assert len(await jobs_of(deps, "t-cancel-ok")) == 0


async def test_schedule_task_action_cancel_huy_job_cua_thread_khac_bi_tu_choi(deps: ToolDeps) -> None:
    """hủy job của THREAD KHÁC bị từ chối - job vẫn còn nguyên (chặn IDOR ở tầng store)"""
    ctx_owner = make_ctx("t-cancel-chu")
    await run(ctx_owner, deps, create_args("job của chủ"))
    [job] = await jobs_of(deps, "t-cancel-chu")

    ctx_khac = make_ctx("t-cancel-la")
    result = await run(ctx_khac, deps, {"action": "cancel", "id": job.id})

    assert "Không tìm thấy" in loi_cua_tool(result)
    still = await deps.scheduler.get_job(ctx_owner.clinic_id, ACCOUNT_ID, "t-cancel-chu", job.id)
    assert still is not None
    assert still.id == job.id, "job của chủ vẫn còn nguyên"


async def test_schedule_task_action_cancel_id_khong_ton_tai_tra_cau_ro_rang_khong_throw(
    deps: ToolDeps,
) -> None:
    """id không tồn tại trả câu rõ ràng, không throw"""
    result = await run(make_ctx("t-cancel-khong-ton-tai"), deps, {"action": "cancel", "id": "khong-ton-tai"})
    assert "Không tìm thấy" in loi_cua_tool(result)


# ------------------------------------------------------------------------------ action update


async def test_schedule_task_action_update_sua_payload_va_lich_doc_lai_thay_dung_gia_tri_moi(
    deps: ToolDeps,
) -> None:
    """sửa payload và lịch - đọc lại thấy đúng giá trị mới"""
    ctx = make_ctx("t-update-ok")
    await run(ctx, deps, create_args("cũ", 30, "message", "nội dung cũ"))
    [job] = await jobs_of(deps, "t-update-ok")

    result = await run(
        ctx,
        deps,
        {"action": "update", "id": job.id, "payload": "nội dung mới", "schedule": every(60)},
    )

    assert isinstance(result, str)
    assert "Đã cập nhật" in result
    sau = await deps.scheduler.get_job(ctx.clinic_id, ACCOUNT_ID, "t-update-ok", job.id)
    assert sau is not None
    assert sau.payload == "nội dung mới"
    assert sau.every_minutes == 60


async def test_schedule_task_action_update_sua_job_cua_thread_khac_bi_tu_choi(deps: ToolDeps) -> None:
    """sửa job của THREAD KHÁC bị từ chối - job vẫn còn nguyên giá trị cũ"""
    ctx_owner = make_ctx("t-update-chu")
    await run(ctx_owner, deps, create_args("cũ", 30, "message", "nội dung cũ"))
    [job] = await jobs_of(deps, "t-update-chu")

    ctx_khac = make_ctx("t-update-la")
    result = await run(ctx_khac, deps, {"action": "update", "id": job.id, "payload": "bị đổi trái phép"})

    assert "Không tìm thấy" in loi_cua_tool(result)
    still = await deps.scheduler.get_job(ctx_owner.clinic_id, ACCOUNT_ID, "t-update-chu", job.id)
    assert still is not None
    assert still.payload == "nội dung cũ"


async def test_schedule_task_action_update_doi_sang_lich_khong_hop_le_thi_bao_loi_all_or_nothing(
    deps: ToolDeps,
) -> None:
    """đổi sang lịch không hợp lệ thì báo lỗi, KHÔNG áp phần thay đổi khác (all-or-nothing)"""
    ctx = make_ctx("t-update-invalid")
    await run(ctx, deps, create_args("cũ", 30, "message", "nội dung cũ"))
    [job] = await jobs_of(deps, "t-update-invalid")

    result = await run(
        ctx,
        deps,
        {
            "action": "update",
            "id": job.id,
            "payload": "nội dung mới lẽ ra không được áp dụng",
            "schedule": every(1),
        },
    )

    assert re.search(r"tối thiểu|spam", loi_cua_tool(result), re.IGNORECASE)
    sau = await deps.scheduler.get_job(ctx.clinic_id, ACCOUNT_ID, "t-update-invalid", job.id)
    assert sau is not None
    assert sau.payload == "nội dung cũ", "lịch hỏng thì payload cũ cũng không được đổi"
    assert sau.every_minutes == 30


# ------------------------------------------------------------------------------ input schema


def parse(deps: ToolDeps, args: dict[str, Any]) -> bool:
    """``inputSchema.safeParse(input).success``"""
    model = create_schedule_task_tool(make_ctx(), deps).input_model
    try:
        model.model_validate(args)
    except ValidationError:
        return False
    return True


def test_schedule_task_schema_dau_vao_action_la_bi_chan_ngay_o_schema(deps: ToolDeps) -> None:
    """action lạ bị chặn ngay ở schema"""
    assert parse(deps, {"action": "delete"}) is False


def test_schedule_task_schema_dau_vao_thieu_truong_theo_action_thi_schema_van_nhan(deps: ToolDeps) -> None:
    """thiếu trường theo action thì schema VẪN NHẬN - chốt chặn nằm ở execute, không ở schema

    The cross-field constraint by action is DELIBERATELY not in the schema (see ``ScheduleTaskWireInput``): a
    rejecting schema builds the input error before ``execute`` runs, the model loses the way to read the
    error sentence and fix itself. The two assertions below record exactly that boundary - change direction
    and they go red.
    """
    assert parse(deps, {"action": "create"}) is True, "create trống phải lọt qua schema"
    assert parse(deps, {"action": "cancel"}) is True, "cancel thiếu id phải lọt qua schema"


def test_schedule_task_schema_dau_vao_goc_cua_schema_la_object_phang_khong_phai_one_of(
    deps: ToolDeps,
) -> None:
    """GỐC của schema là object phẳng, KHÔNG phải oneOf - DeepSeek chối cả request nếu là oneOf"""
    goc = create_schedule_task_tool(make_ctx(), deps).parameters
    assert goc["type"] == "object"
    assert "oneOf" not in goc
    assert "anyOf" not in goc, "union phải nằm lồng bên trong, không được ở nút gốc"
    # A NESTED union is still valid - assert it too so nobody "fixes" the whole tree by mistake
    lich = goc["properties"]["schedule"]
    assert isinstance(lich["anyOf"], list), "schedule vẫn phải là union 4 dạng"
    assert len(lich["anyOf"]) == 4


def test_schedule_task_schema_dau_vao_schedule_kind_once_nhan_ca_2_dang_date_time_va_in_minutes(
    deps: ToolDeps,
) -> None:
    """schedule.kind='once' nhận cả 2 dạng date+time và inMinutes (không phải discriminatedUnion, không
    ném lỗi)"""
    assert parse(
        deps,
        {
            "action": "create",
            "name": "x",
            "kind": "message",
            "payload": "y",
            "schedule": {"kind": "once", "date": "2026-08-01", "time": "15:00"},
        },
    )
    assert parse(
        deps,
        {
            "action": "create",
            "name": "x",
            "kind": "message",
            "payload": "y",
            "schedule": {"kind": "once", "inMinutes": 30},
        },
    )


def test_schedule_task_schema_dau_vao_in_minutes_vuot_tran_525600_bi_chan_ngay_o_schema(
    deps: ToolDeps,
) -> None:
    """inMinutes vượt trần 525600 (1 năm) bị chặn ngay ở schema, không lọt xuống tới datetime gây overflow
    (Mục M3)"""
    assert (
        parse(
            deps,
            {
                "action": "create",
                "name": "x",
                "kind": "message",
                "payload": "y",
                "schedule": {"kind": "once", "inMinutes": 999_999_999},
            },
        )
        is False
    )


# ------------------------------------------------------------------------------ missing parameters


def truong_thieu(loi: str) -> list[str]:
    """Read only the DYNAMIC part of the error sentence - the list of fields the validation really caught.

    It must be split out instead of ``assert re.search("schedule", loi)``: the STATIC sentence that comes with
    it (``action='create' cần đủ: name, kind, payload, schedule.``) already contains the names of all 4
    fields,
    so a text-search assertion over the whole string stays GREEN even when the by-name part is removed.
    """
    m = re.search(r"Thiếu hoặc sai tham số: ([^.]*)\.", loi)
    return [s.strip() for s in m.group(1).split(",")] if m else []


async def test_schedule_task_thieu_tham_so_create_thieu_schedule_neu_dich_danh_truong_thieu(
    deps: ToolDeps,
) -> None:
    """create thiếu schedule: nêu ĐÍCH DANH trường thiếu, KHÔNG tạo job"""
    ctx = make_ctx("t-thieu-schedule")
    result = await run(ctx, deps, {"action": "create", "name": "x", "kind": "message", "payload": "y"})

    loi = loi_cua_tool(result)
    assert truong_thieu(loi) == ["schedule"], "phải nêu đúng trường thiếu để model gọi lại đúng ngay lần sau"
    assert "cần đủ" in loi, "kèm cả câu nhắc yêu cầu của action"
    assert len(await jobs_of(deps, "t-thieu-schedule")) == 0, "không được ghi job nào"


async def test_schedule_task_thieu_tham_so_create_thieu_ca_name_lan_payload_liet_ke_du(
    deps: ToolDeps,
) -> None:
    """create thiếu cả name lẫn payload: liệt kê ĐỦ, không dừng ở trường đầu tiên"""
    ctx = make_ctx("t-thieu-nhieu")
    result = await run(ctx, deps, {"action": "create", "kind": "message", "schedule": every(30)})

    assert truong_thieu(loi_cua_tool(result)) == ["name", "payload"]
    assert len(await jobs_of(deps, "t-thieu-nhieu")) == 0


async def test_schedule_task_thieu_tham_so_cancel_thieu_id_neu_dich_danh_id_kem_loi_ra(
    deps: ToolDeps,
) -> None:
    """cancel thiếu id: nêu đích danh id, kèm lối ra (gọi list), không throw"""
    result = await run(make_ctx("t-thieu-id"), deps, {"action": "cancel"})

    loi = loi_cua_tool(result)
    assert truong_thieu(loi) == ["id"]
    assert "list" in loi, "phải chỉ đường lấy id thay vì để model tự đoán"


async def test_schedule_task_thieu_tham_so_update_thieu_id_cung_bi_chan(deps: ToolDeps) -> None:
    """update thiếu id cũng bị chặn - không âm thầm sửa nhầm job khác"""
    result = await run(make_ctx("t-update-thieu-id"), deps, {"action": "update", "payload": "nội dung mới"})

    assert truong_thieu(loi_cua_tool(result)) == ["id"]


async def test_schedule_task_thieu_tham_so_truong_thua_khong_thuoc_action_bi_bo_qua(deps: ToolDeps) -> None:
    """trường THỪA không thuộc action bị bỏ qua, không làm hỏng lượt gọi hợp lệ"""
    # The flat schema lets ``id`` travel with a create; the strict union strips it. If the narrowing used a
    # strict model this valid call would break for nothing.
    ctx = make_ctx("t-truong-thua")
    result = await run(
        ctx,
        deps,
        {**create_args("x", 30, "message", "y"), "id": "id-thừa-model-tự-thêm"},
    )

    assert isinstance(result, str)
    assert "Đã tạo lịch" in result
    assert len(await jobs_of(deps, "t-truong-thua")) == 1


# ------------------------------------------------------------------------------ dedupe

LICH_NHAC: dict[str, Any] = {
    "action": "create",
    "name": "Nhắc đóng học phí Phật học",
    "kind": "message",
    "schedule": {"kind": "once", "date": ONCE_TEST_DATE, "time": ONCE_TEST_TIME},
}


async def test_schedule_task_khong_tao_ban_trung_ca_that_cung_ten_cung_moc_payload_khac_van_mot_job(
    deps: ToolDeps,
) -> None:
    """ca THẬT: cùng tên + cùng mốc, payload model viết khác đi -> vẫn chỉ MỘT job

    The real case of 2026-08-20 (read from the trace): the bot set the reminder in turn 2, and in turn 3 the
    user only wrote "okay cảm ơn bạn" and the bot CREATED THE SAME ONE AGAIN. ``name`` / ``kind`` /
    ``schedule``
    are identical, the ``payload`` differs (the model rewrote the sentence), so the key has no ``payload``.
    """
    ctx = make_ctx("t-trung-that")

    lan1 = await run(
        ctx,
        deps,
        {
            **LICH_NHAC,
            "payload": "🔔 Kim Phượng ơi, nhớ đóng tiền học phí Phật học nhé! Hạn chót nộp là ngày 05/09/2026.",
        },
    )
    lan2 = await run(
        ctx,
        deps,
        {
            **LICH_NHAC,
            "payload": "Kim Phượng ơi, hôm nay nhớ đóng tiền học phí Phật học nhé. "
            "Hạn chót nộp là ngày 05/09/2026.",
        },
    )

    jobs = await jobs_of(deps, "t-trung-that")
    assert len(jobs) == 1, "tạo ra bản trùng - người dùng sẽ nhận hai tin cùng lúc"
    assert isinstance(lan1, str)
    assert isinstance(lan2, str)
    assert "Đã tạo lịch" in lan1
    assert "ĐÃ CÓ SẴN" in lan2, "lần hai phải nói rõ lịch đã có, không phải vừa tạo thêm"
    assert jobs[0].id in lan2, "phải trả về id của job đã có để model nói đúng"
    assert not lan2.startswith("Đã tạo lịch"), "không được nói là vừa tạo"


async def test_schedule_task_khong_tao_ban_trung_ket_qua_lan_hai_khong_phai_dau_hieu_loi(
    deps: ToolDeps,
) -> None:
    """kết quả lần hai KHÔNG phải dấu hiệu lỗi - trạng thái mong muốn đã có sẵn"""
    # The repo decided: the FAILING branch returns the object ``{ok: False, loi}`` through
    # ``ket_qua_loi``, the
    # success branch returns a bare string. An existing schedule is a SUCCESS - returning an error here would
    # trigger ``tool-loop-guard`` and make the model think it just failed.
    ctx = make_ctx("t-trung-khong-loi")
    await run(ctx, deps, {**LICH_NHAC, "payload": "lần một"})
    lan2 = await run(ctx, deps, {**LICH_NHAC, "payload": "lần hai"})
    ket_qua_thanh_cong(lan2)


async def test_schedule_task_khong_tao_ban_trung_hai_viec_khac_nhau_vao_cung_mot_gio_van_dat_duoc_ca_hai(
    deps: ToolDeps,
) -> None:
    """HAI việc khác nhau vào CÙNG một giờ vẫn đặt được cả hai"""
    # Constraint chosen by the user: "11:00 nhắc đóng học phí" and "11:00 nhắc họp phụ huynh" are two real
    # things. The key having ``name`` is exactly to keep this case - dropping ``name`` would block it wrongly.
    ctx = make_ctx("t-hai-viec")
    await run(ctx, deps, {**LICH_NHAC, "payload": "đóng học phí"})
    khac = await run(ctx, deps, {**LICH_NHAC, "name": "Nhắc họp phụ huynh", "payload": "họp phụ huynh"})

    assert len(await jobs_of(deps, "t-hai-viec")) == 2, "chặn oan lịch thứ hai"
    assert isinstance(khac, str)
    assert "Đã tạo lịch" in khac
    assert "LƯU Ý" in khac, "phải nhắc model rằng đã có lịch khác cùng mốc giờ"
    assert "Nhắc đóng học phí Phật học" in khac, "phải nêu tên lịch cùng mốc để model nói lại được"


async def test_schedule_task_khong_tao_ban_trung_ten_chi_khac_hoa_thuong_va_khoang_trang_thua(
    deps: ToolDeps,
) -> None:
    """tên chỉ khác hoa/thường và khoảng trắng thừa vẫn tính là trùng"""
    ctx = make_ctx("t-trung-chuan-hoa")
    await run(ctx, deps, {**LICH_NHAC, "payload": "x"})
    lan2 = await run(ctx, deps, {**LICH_NHAC, "name": "  nhắc ĐÓNG   học phí Phật học ", "payload": "y"})

    assert len(await jobs_of(deps, "t-trung-chuan-hoa")) == 1
    assert isinstance(lan2, str)
    assert "ĐÃ CÓ SẴN" in lan2


async def test_schedule_task_khong_tao_ban_trung_lich_da_tat_thi_dat_lai_duoc(deps: ToolDeps) -> None:
    """lịch ĐÃ TẮT thì đặt lại được - job đó không bao giờ chạy nữa"""
    # Blocking here is wrong: the user asking to set again the very reminder they just turned off is a valid
    # request, and the old job is never picked up by the scheduler.
    ctx = make_ctx("t-da-tat")
    await run(ctx, deps, {**LICH_NHAC, "payload": "x"})
    [cu] = await jobs_of(deps, "t-da-tat")
    await deps.scheduler.set_enabled(ctx.clinic_id, ACCOUNT_ID, "t-da-tat", cu.id, False)

    lan2 = await run(ctx, deps, {**LICH_NHAC, "payload": "y"})

    assert isinstance(lan2, str)
    assert "Đã tạo lịch" in lan2, "lịch đã tắt mà vẫn bị coi là trùng"
    assert len(await jobs_of(deps, "t-da-tat")) == 2


async def test_schedule_task_khong_tao_ban_trung_thread_khac_khong_anh_huong_nhau(deps: ToolDeps) -> None:
    """thread KHÁC không ảnh hưởng nhau"""
    a = make_ctx("t-pham-vi-a")
    b = make_ctx("t-pham-vi-b")
    await run(a, deps, {**LICH_NHAC, "payload": "x"})
    ket_qua_b = await run(b, deps, {**LICH_NHAC, "payload": "x"})

    assert isinstance(ket_qua_b, str)
    assert "Đã tạo lịch" in ket_qua_b, "khử trùng bị rò sang cuộc trò chuyện khác"
    assert len(await jobs_of(deps, "t-pham-vi-b")) == 1


# ------------------------------------------------------------------------------ policy hook (clinic)


class _JobPolicy(PermissivePolicyHooks):
    def __init__(self, decision: JobDecision) -> None:
        self.decision = decision
        self.seen: list[CreateScheduledJobInput] = []

    async def check_job(self, ctx: PolicyContext, job: CreateScheduledJobInput) -> JobDecision:
        self.seen.append(job)
        return self.decision


async def test_schedule_task_policy_check_job_deny_tra_ly_do_cua_hook_khong_tao_job() -> None:
    """PolicyHooks.check_job DENY -> ket_qua_loi với lý do của hook, job không được lưu"""
    policy = _JobPolicy(JobDecision(action=JobAction.DENY, reason="Kênh này không cho đặt lịch agent."))
    deps = make_tool_deps(schedule_parser=TzParser(), policy=policy)

    result = await run(make_ctx("t-deny"), deps, create_args("x", 30, "agent", "prompt"))

    assert loi_cua_tool(result) == "Kênh này không cho đặt lịch agent."
    assert len(await jobs_of(deps, "t-deny")) == 0
    assert len(policy.seen) == 1
    assert policy.seen[0].thread_id == "t-deny"
    assert policy.seen[0].origin == "agent_tool"
    assert policy.seen[0].thread_type == 1


async def test_schedule_task_policy_check_job_deny_khong_co_ly_do_dung_cau_chung() -> None:
    """DENY không kèm lý do -> câu tiếng Việt chung, vẫn là ket_qua_loi"""
    deps = make_tool_deps(schedule_parser=TzParser(), policy=_JobPolicy(JobDecision(action=JobAction.DENY)))

    result = await run(make_ctx("t-deny-chung"), deps, create_args("x"))

    assert "không tạo được lịch này" in loi_cua_tool(result)
    assert len(await jobs_of(deps, "t-deny-chung")) == 0


async def test_schedule_task_policy_check_job_downgrade_van_tao_nhung_bao_model_la_ban_nhap() -> None:
    """DOWNGRADE_TO_DRAFT -> vẫn tạo job, kết quả báo chỉ soạn bản nháp cho nhân viên duyệt (thành công)"""
    deps = make_tool_deps(
        schedule_parser=TzParser(),
        policy=_JobPolicy(JobDecision(action=JobAction.DOWNGRADE_TO_DRAFT)),
    )

    result = await run(make_ctx("t-downgrade"), deps, create_args("x", 30, "agent", "prompt"))

    ket_qua = ket_qua_thanh_cong(result)
    assert "Đã tạo lịch" in ket_qua
    assert "BẢN NHÁP" in ket_qua
    assert len(await jobs_of(deps, "t-downgrade")) == 1
    assert len(scheduler_of(deps).created) == 1


async def test_schedule_task_policy_check_job_khong_chay_khi_lich_trung_hoac_cham_tran() -> None:
    """hook chỉ được hỏi sau khi qua kiểm trùng và trần - lời gọi trùng khít không đụng tới policy"""
    policy = _JobPolicy(JobDecision())
    deps = make_tool_deps(schedule_parser=TzParser(), policy=policy)
    ctx = make_ctx("t-hook-thu-tu")
    await run(ctx, deps, create_args("x"))
    await run(ctx, deps, create_args("x"))

    assert len(policy.seen) == 1
