# ported from: src/server/routes/schedule-routes.test.ts
"""API ``/admin/schedules`` - the "Schedules" page of the dashboard.

Two groups carry the weight: (1) ISOLATION - the original proved that a job of thread B cannot be touched with the
(accountId, threadId) of thread A even when its 12-hex id is known; the contract here addresses a job by ``job_id``
inside ONE clinic, so the isolation that is proved is the clinic boundary (a job of another clinic is "not found");
(2) "Run now" must NOT shift the real schedule - ``next_run_at`` / ``enabled`` / ``run_count`` measured BEFORE and
AFTER, even when the send succeeds.

The caller identity is package B1's authentication (not in this worktree): the tests override
``get_schedule_context``. Test names are the snake_case form of ``describe_it``; the original Vietnamese title is
the docstring. Status codes follow ``ErrorCode``: the original 400 is 422 (``validation_failed`` /
``invalid_schedule``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from pema.api.deps import API_PREFIX
from pema.api.errors import install_error_handlers
from pema.api.routers import admin_schedules
from pema.api.routers.admin_schedules import ScheduleContext, get_schedule_context
from pema.scheduler.admin_service import ScheduleAdminService
from pema.scheduler.testing_env import ACC, Env

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]
THREAD = "t-schedule-route"
BASE_URL = f"{API_PREFIX}/admin/schedules"


@pytest_asyncio.fixture
async def api(make_env: EnvMaker) -> AsyncIterator[tuple[httpx.AsyncClient, Env, FastAPI]]:
    env = make_env()
    env.make_thread(THREAD)
    env.make_thread("t-schedule-route-khac")
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(admin_schedules.router, prefix=API_PREFIX)
    service = ScheduleAdminService(env.deps)
    app.dependency_overrides[get_schedule_context] = lambda: ScheduleContext(
        clinic_id=env.clinic_id, actor="staff-1", service=service
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, env, app


def body(**overrides: Any) -> dict[str, Any]:
    return {
        "account_id": ACC,
        "thread_id": THREAD,
        "thread_type": 0,
        "name": "Job test",
        "kind": "message",
        "payload": "Nhắc nhở thử nghiệm",
        "schedule": {"kind": "once", "in_minutes": 120},
        **overrides,
    }


async def create(client: httpx.AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post(BASE_URL, json=body(**overrides))
    assert response.status_code == 201, response.text
    job: dict[str, Any] = response.json()
    return job


async def listing(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get(BASE_URL, params={"account_id": ACC})
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()
    return items


# ------------------------------------------------------------------------------------------ GET


async def test_get_schedules_without_a_signed_in_caller_is_401(make_env: EnvMaker) -> None:
    """chưa login -> 401"""
    env = make_env()
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(admin_schedules.router, prefix=API_PREFIX)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(BASE_URL)).status_code == 501, (
            "chưa nối dịch vụ: giữ nguyên 501 của skeleton"
        )
        app.state.schedule_admin = ScheduleAdminService(env.deps)
        assert (await client.get(BASE_URL)).status_code == 401


async def test_get_schedules_lists_the_jobs_of_the_clinic_optionally_filtered_by_account(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """trả danh sách job (lọc theo account nếu có)"""
    client, _, _ = api
    job = await create(client)
    assert any(j["id"] == job["id"] for j in await listing(client))
    other = await client.get(BASE_URL, params={"account_id": "acc-khac"})
    assert other.json() == []
    everything = await client.get(BASE_URL)
    assert any(j["id"] == job["id"] for j in everything.json())


# ----------------------------------------------------------------------------------------- POST


async def test_post_schedules_creates_a_message_job_visible_in_the_list(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """tạo job kind=message thành công, xuất hiện trong danh sách"""
    client, _, _ = api
    job = await create(client, name="Nhắc họp")
    assert job["name"] == "Nhắc họp"
    assert job["enabled"] is True
    assert job["run_count"] == 0
    assert job["next_run_at"]
    assert job["created_by"] == "staff-1"
    assert job["origin"] == "staff"
    assert any(j["id"] == job["id"] for j in await listing(client))


async def test_post_schedules_unknown_account_is_rejected(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """account không tồn tại -> bị từ chối (gốc: 400, giờ 422)"""
    client, _, _ = api
    response = await client.post(BASE_URL, json=body(account_id="acc-khong-ton-tai"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_post_schedules_a_thread_never_seen_is_rejected(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """thread chưa từng ghi nhận -> bị từ chối"""
    client, _, _ = api
    response = await client.post(BASE_URL, json=body(thread_id="t-chua-tung-thay"))
    assert response.status_code == 422


async def test_post_schedules_an_every_schedule_denser_than_the_anti_spam_threshold_is_blocked_with_the_reason(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """lịch every quá dày (dưới ngưỡng chống spam) bị chặn kèm lý do"""
    client, _, _ = api
    response = await client.post(BASE_URL, json=body(schedule={"kind": "every", "minutes": 1}))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_schedule"
    assert "spam" in response.json()["error"]["message"]


async def test_post_schedules_in_minutes_above_the_ceiling_is_a_readable_error_not_a_500(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """inMinutes vượt trần -> lỗi có lý do rõ ràng, KHÔNG phải 500 (Mục M3: chặn trước khi phép cộng ngày tháng tràn)"""
    client, _, _ = api
    response = await client.post(BASE_URL, json=body(schedule={"kind": "once", "in_minutes": 999_999_999}))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_schedule"


async def test_post_schedules_every_minutes_above_525600_is_a_readable_error_not_a_500(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """every.minutes vượt trần 525600 -> lỗi đọc được, KHÔNG phải 500 (cùng lỗ tràn đã vá cho inMinutes)"""
    client, _, _ = api
    response = await client.post(BASE_URL, json=body(schedule={"kind": "every", "minutes": 999_999_999}))
    assert response.status_code == 422
    assert len(response.json()["error"]["message"]) > 0


async def test_post_schedules_the_thread_cap_blocks_the_creation_of_one_job_too_many(
    make_env: EnvMaker,
) -> None:
    """(trần SCHEDULER_MAX_JOBS_PER_THREAD áp cho cả đường tạo job từ web)"""
    env = make_env(tuning={"SCHEDULER_MAX_JOBS_PER_THREAD": 2, "SCHEDULER_SEND_GAP_MS": 0})
    env.make_thread(THREAD)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(admin_schedules.router, prefix=API_PREFIX)
    service = ScheduleAdminService(env.deps)
    app.dependency_overrides[get_schedule_context] = lambda: ScheduleContext(
        env.clinic_id, "staff-1", service
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await create(client, name="job 1")
        await create(client, name="job 2")
        response = await client.post(BASE_URL, json=body(name="job 3"))
    assert response.status_code == 422
    assert "trần" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------------------- PATCH


async def test_patch_schedules_edits_name_and_payload(api: tuple[httpx.AsyncClient, Env, FastAPI]) -> None:
    """sửa tên/nội dung thành công"""
    client, _, _ = api
    job = await create(client, name="Trước khi sửa")
    response = await client.patch(
        f"{BASE_URL}/{job['id']}", json={"name": "Đã sửa", "payload": "Nội dung mới"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Đã sửa"
    assert response.json()["payload"] == "Nội dung mới"


async def test_patch_schedules_enables_and_disables_through_enabled(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """bật/tắt qua enabled"""
    client, _, _ = api
    job = await create(client)
    response = await client.patch(f"{BASE_URL}/{job['id']}", json={"enabled": False})
    assert response.json()["enabled"] is False


async def test_patch_schedules_re_enabling_a_disabled_job_must_pass_the_thread_cap(
    make_env: EnvMaker,
) -> None:
    """bật LẠI job đang tắt phải qua đúng trần SCHEDULER_MAX_JOBS_PER_THREAD - tạo đủ trần, tắt bớt, tạo thêm rồi bật lại hết phải bị chặn (Mục M4)"""
    env = make_env(tuning={"SCHEDULER_MAX_JOBS_PER_THREAD": 2, "SCHEDULER_SEND_GAP_MS": 0})
    thread = "t-m4-cap-enable"
    env.make_thread(thread)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(admin_schedules.router, prefix=API_PREFIX)
    service = ScheduleAdminService(env.deps)
    app.dependency_overrides[get_schedule_context] = lambda: ScheduleContext(
        env.clinic_id, "staff-1", service
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        job1 = await create(client, thread_id=thread, name="job 1")
        await create(client, thread_id=thread, name="job 2")  # 2 enabled jobs - at the cap
        await client.patch(f"{BASE_URL}/{job1['id']}", json={"enabled": False})  # make room
        await create(client, thread_id=thread, name="job 3")  # at the cap again (job2 + job3)

        # re-enabling job1 would make 3 enabled jobs, above the cap of 2 - MUST be blocked
        response = await client.patch(f"{BASE_URL}/{job1['id']}", json={"enabled": True})
        assert response.status_code == 422
        assert "trần" in response.json()["error"]["message"]

        items = (await client.get(BASE_URL, params={"account_id": ACC})).json()
    assert next(j for j in items if j["id"] == job1["id"])["enabled"] is False, (
        "PATCH bị chặn không được lén bật lên"
    )


async def test_patch_schedules_unknown_job_is_404(api: tuple[httpx.AsyncClient, Env, FastAPI]) -> None:
    """job không tồn tại -> 404"""
    client, _, _ = api
    response = await client.patch(f"{BASE_URL}/khong-ton-tai", json={"name": "x"})
    assert response.status_code == 404


async def test_patch_schedules_a_job_of_another_clinic_is_404_and_untouched(
    api: tuple[httpx.AsyncClient, Env, FastAPI], make_env: EnvMaker
) -> None:
    """job của PHÒNG KHÁM KHÁC -> 404, không sửa được (thay cho IDOR theo thread của bản gốc)"""
    client, env, app = api
    other = make_env()
    other_job = await other.make_job(thread_id="t-clinic-khac")

    response = await client.patch(f"{BASE_URL}/{other_job.id}", json={"name": "Bị đổi trộm"})

    assert response.status_code == 404, "job của phòng khám khác phải coi như không tồn tại"
    still = await other.deps.jobs.get_job_unscoped(other.clinic_id, other_job.id)
    assert still is not None
    assert still.name == other_job.name, "tên KHÔNG được đổi qua đường vượt phòng khám"
    assert app is not None
    assert env.clinic_id != other.clinic_id


async def test_patch_schedules_a_new_schedule_is_parsed_with_the_same_rules_as_creation(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """đổi lịch qua PATCH đi qua đúng parseSchedule (ngưỡng chống spam) như lúc tạo"""
    client, _, _ = api
    job = await create(client)
    rejected = await client.patch(
        f"{BASE_URL}/{job['id']}", json={"schedule": {"kind": "every", "minutes": 1}}
    )
    assert rejected.status_code == 422
    accepted = await client.patch(
        f"{BASE_URL}/{job['id']}", json={"schedule": {"kind": "every", "minutes": 45}}
    )
    assert accepted.status_code == 200
    assert accepted.json()["every_minutes"] == 45
    assert accepted.json()["schedule_kind"] == "every"


# --------------------------------------------------------------------------------------- DELETE


async def test_delete_schedules_removes_the_job(api: tuple[httpx.AsyncClient, Env, FastAPI]) -> None:
    """xóa thành công"""
    client, _, _ = api
    job = await create(client)
    response = await client.delete(f"{BASE_URL}/{job['id']}")
    assert response.status_code == 204
    assert not any(j["id"] == job["id"] for j in await listing(client))
    assert (await client.delete(f"{BASE_URL}/{job['id']}")).status_code == 404


async def test_delete_schedules_a_job_of_another_clinic_is_404_and_stays(
    api: tuple[httpx.AsyncClient, Env, FastAPI], make_env: EnvMaker
) -> None:
    """job của PHÒNG KHÁM KHÁC -> 404, job vẫn còn nguyên"""
    client, _, _ = api
    other = make_env()
    other_job = await other.make_job(thread_id="t-clinic-khac")
    response = await client.delete(f"{BASE_URL}/{other_job.id}")
    assert response.status_code == 404
    assert await other.deps.jobs.get_job_unscoped(other.clinic_id, other_job.id) is not None


# ---------------------------------------------------------------------------- POST /{id}/run


async def test_run_schedule_a_job_of_another_clinic_is_404(
    api: tuple[httpx.AsyncClient, Env, FastAPI], make_env: EnvMaker
) -> None:
    """job của PHÒNG KHÁM KHÁC -> 404, không chạy thử được"""
    client, _, _ = api
    other = make_env()
    other_job = await other.make_job(thread_id="t-clinic-khac")
    assert (await client.post(f"{BASE_URL}/{other_job.id}/run")).status_code == 404
    assert other.channel.sent == []


async def test_run_schedule_really_sends_but_next_run_at_enabled_run_count_do_not_change_even_twice(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """gửi thật NHƯNG next_run_at/enabled/run_count của job KHÔNG đổi, kể cả gửi 2 lần liên tiếp"""
    client, env, _ = api
    job = await create(client, name="Job chạy thử", payload="Tin chạy thử nghiệm")

    first = await client.post(f"{BASE_URL}/{job['id']}/run")
    assert first.status_code == 200
    assert first.json()["status"] == "ok"
    assert [p.text for p in env.channel.sent] == ["Tin chạy thử nghiệm"]

    after1 = next(j for j in await listing(client) if j["id"] == job["id"])
    assert after1["next_run_at"] == job["next_run_at"], "next_run_at KHÔNG được đổi sau khi chạy thử"
    assert after1["enabled"] is True, (
        "job 'once' KHÔNG được tự tắt sau khi chạy thử (bug: maxRuns=1 dùng hết suất)"
    )
    assert after1["run_count"] == 0, "run_count KHÔNG được tăng - đây không phải lần chạy THẬT"

    second = await client.post(f"{BASE_URL}/{job['id']}/run")
    assert second.json()["status"] == "ok"
    assert len(env.channel.sent) == 2, "lần chạy thử thứ 2 vẫn phải gửi được - suất chưa hề bị dùng ở lần 1"
    after2 = next(j for j in await listing(client) if j["id"] == job["id"])
    assert (after2["next_run_at"], after2["enabled"], after2["run_count"]) == (job["next_run_at"], True, 0)


async def test_run_schedule_a_job_with_a_run_still_running_is_409_no_trial_on_top_of_it(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """job còn 1 lượt 'running' (tick thật đang dispatch dở, chưa chốt sổ) -> 409, không được chạy thử chồng lên (I3)"""
    client, env, _ = api
    job = await create(client, name="Job đang chạy dở")
    await env.deps.runs.open_run(env.clinic_id, job["id"])  # a real tick dispatched, not yet finished

    response = await client.post(f"{BASE_URL}/{job['id']}/run")

    assert response.status_code == 409
    assert "đang chạy" in response.json()["error"]["message"]
    assert env.channel.sent == []


# --------------------------------------------------------------------------- GET /{id}/runs


async def test_list_schedule_runs_a_job_of_another_clinic_is_404(
    api: tuple[httpx.AsyncClient, Env, FastAPI], make_env: EnvMaker
) -> None:
    """job của PHÒNG KHÁM KHÁC -> 404"""
    client, _, _ = api
    other = make_env()
    other_job = await other.make_job(thread_id="t-clinic-khac")
    assert (await client.get(f"{BASE_URL}/{other_job.id}/runs")).status_code == 404


async def test_list_schedule_runs_returns_the_history_after_a_trial_with_a_null_turn_id_for_a_message_job(
    api: tuple[httpx.AsyncClient, Env, FastAPI],
) -> None:
    """trả lịch sử sau khi chạy thử, kèm turn_id null cho job kind=message"""
    client, _, _ = api
    job = await create(client, name="Job có lịch sử")
    await client.post(f"{BASE_URL}/{job['id']}/run")

    response = await client.get(f"{BASE_URL}/{job['id']}/runs")

    assert response.status_code == 200
    runs = response.json()
    assert len(runs) >= 1
    assert runs[0]["status"] == "ok"
    assert runs[0]["turn_id"] is None, "kind=message không chạm agent nên không có turn_id"
