"""Closed loop 5 (package G): a CRM rule -> scheduler -> proactive message, per profile.

The whole chain on real Postgres and Redis: a doctor-approved template and a rule set to ``auto_reminder`` (the
staff screens of B1/B2), the CRM runner creating the job (``dedupe_key`` = task key), the scheduler of the worker
running the job when due, then:

* ``patient_channel``: the text goes to a ``followup_draft`` review item, nothing is sent;
* ``staff_assistant``: the template text is sent through the channel, as a proactive message;
* a birthday is never sent automatically (the rule refuses ``auto_reminder``, the patient has no job);
* a patient with ``marketing_opt_out`` gets no job from a marketing rule.

The runner is driven by hand with the demo clock (2026-09-20 09:00) and the scheduler is ticked by hand: no
timer, no sleep.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pema.api.clinic_testing import DEMO_NOW
from pema.clinic.crm_rules.runner import CrmRulesRunner, RunReport
from pema.clinic.crm_rules.sql_store import SqlCrmRuleStore
from pema.composition.testing import Loop, LoopFactory, scripted
from pema.scheduler.scheduler_loop import SchedulerLoop
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.scheduler import JobOrigin, ScheduledJob

pytestmark = [pytest.mark.db, pytest.mark.redis]

D1_TEXT = "Phòng khám hỏi thăm bạn sau buổi điều trị hôm qua. Cần gì xin nhắn lại cho chúng tôi ạ."


async def approved_template(loop: Loop, key: str, body: str, *, marketing: bool = False) -> None:
    """A template written by the owner and signed off by a doctor (the only way to an ACTIVE template)."""
    owner = await loop.staff("owner")
    created = await owner.post(
        "/api/v1/admin/templates",
        json={"template_key": key, "title": f"Mẫu {key}", "body": body, "marketing": marketing},
    )
    assert created.status_code in (200, 201), created.text
    doctor = await loop.staff("doctor.mai")
    approved = await doctor.post(
        f"/api/v1/admin/templates/{created.json()['id']}/approve", json={"version": created.json()["version"]}
    )
    assert approved.status_code == 200, approved.text


async def set_rule_mode(loop: Loop, rule_key: str, send_mode: str) -> Any:
    manager = await loop.staff("manager")
    listed = await manager.get("/api/v1/admin/rules")
    assert listed.status_code == 200, listed.text
    rule = next(r for r in listed.json() if r["rule_key"] == rule_key)
    return await manager.patch(
        f"/api/v1/admin/rules/{rule_key}", json={"version": rule["version"], "send_mode": send_mode}
    )


async def customer_writes_first(loop: Loop, *, held: bool) -> None:
    """A proactive message needs a thread the agent has seen (a customer who wrote before): the verified
    customer says hello and the system answers (held as a draft in ``patient_channel``, sent in
    ``staff_assistant``). Afterwards the thread exists for the scheduler."""
    await loop.send_zalo_text("xin chào phòng khám", uid="demo-uid-025")
    if held:
        await loop.wait_review_items(1)
    else:
        await loop.wait_sent(1)


async def run_crm(loop: Loop) -> RunReport:
    runner = CrmRulesRunner(SqlCrmRuleStore(loop.api.db), loop.api.scheduler)
    return await runner.run_clinic(loop.clinic_id, DEMO_NOW)


async def crm_jobs(loop: Loop) -> list[ScheduledJob]:
    jobs = await loop.api.scheduler.list_jobs(loop.clinic_id)
    return [j for j in jobs if j.origin is JobOrigin.CRM_RULE]


async def tick_when_due(loop: Loop, job: ScheduledJob) -> None:
    """Tick the scheduler of the WORKER one minute after the job is due, and wait for the run to finish."""
    assert job.next_run_at is not None
    due = datetime.fromisoformat(job.next_run_at.replace("Z", "+00:00")).astimezone(UTC)
    scheduler = SchedulerLoop(loop.worker_rt.scheduler_deps)
    await scheduler.run_tick(loop.clinic_id, due + timedelta(minutes=1))
    await scheduler.wait_idle()


async def test_patient_channel_viec_den_han_thanh_ban_nhap_cho_duyet_khong_gui_thang(
    make_loop: LoopFactory,
) -> None:
    """quy tắc d1 + mẫu đã duyệt -> job -> scheduler -> followup_draft chờ duyệt, KHÔNG gửi trực tiếp"""
    async with await make_loop.open_fresh(scripted("không dùng"), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        await customer_writes_first(loop, held=True)
        await approved_template(loop, "crm.d1", D1_TEXT)
        mode = await set_rule_mode(loop, "d1", "auto_reminder")
        assert mode.status_code == 200, mode.text

        report = await run_crm(loop)
        assert report.jobs_created == 1, report
        (job,) = await crm_jobs(loop)
        assert job.payload == "crm.d1", "job mang KHÓA mẫu, không mang chữ"
        assert job.patient_id is not None

        await tick_when_due(loop, job)

        items = await loop.wait_review_items(2)
        (item,) = [i for i in items if i["kind"] == "followup_draft"]
        assert item["origin"] == "crm_rule"
        assert item["draft_text"] == D1_TEXT
        assert loop.bot.sent == [], "patient_channel: tin chủ động không tự gửi"
        assert loop.model.count == 1, "chỉ lượt trả lời lời chào dùng LLM; job kind=message không gọi LLM"


async def test_staff_assistant_viec_den_han_gui_mau_da_duyet_qua_kenh_tin_chu_dong(
    make_loop: LoopFactory,
) -> None:
    """hồ sơ staff_assistant -> cùng chuỗi nhưng chữ của mẫu được gửi thẳng, không phải khóa mẫu"""
    async with await make_loop.open_fresh(scripted("không dùng"), PolicyProfileKey.STAFF_ASSISTANT) as loop:
        await customer_writes_first(loop, held=False)
        await approved_template(loop, "crm.d1", D1_TEXT)
        assert (await set_rule_mode(loop, "d1", "auto_reminder")).status_code == 200
        assert (await run_crm(loop)).jobs_created == 1
        (job,) = await crm_jobs(loop)

        await tick_when_due(loop, job)

        sent = await loop.wait_sent(2)
        assert sent[1] == ("demo-uid-025", D1_TEXT, None)
        assert "crm.d1" not in sent[1][1]
        assert await loop.review_items() == []


async def test_sinh_nhat_khong_bao_gio_tu_gui(make_loop: LoopFactory) -> None:
    """sinh nhật: quy tắc từ chối auto_reminder và bệnh nhân sinh nhật không có job nào"""
    async with await make_loop.open_fresh(scripted("không dùng"), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        refused = await set_rule_mode(loop, "birthday", "auto_reminder")
        assert refused.status_code >= 400, refused.text

        await run_crm(loop)

        names = {j.name for j in await crm_jobs(loop)}
        assert not any("birthday" in name for name in names)
        assert loop.bot.sent == []


async def test_marketing_opt_out_chan_tac_vu_va_job_tiep_thi(make_loop: LoopFactory) -> None:
    """khách marketingOptOut (P030, "khách cũ 180 ngày"): quy tắc tiếp thị dormant180 không tạo việc, không có
    job; khách không opt-out (P031, dormant90) vẫn có việc - chặn đúng người"""
    async with await make_loop.open_fresh(scripted("không dùng"), PolicyProfileKey.PATIENT_CHANNEL) as loop:
        await approved_template(loop, "crm.dormant180", "Lâu rồi phòng khám chưa gặp bạn.", marketing=True)
        assert (await set_rule_mode(loop, "dormant180", "auto_reminder")).status_code == 200
        assert (await set_rule_mode(loop, "dormant90", "auto_reminder")).status_code == 200

        await run_crm(loop)

        tasks = await _tasks(loop)
        assert ("P031", "dormant90") in tasks, "khách không opt-out vẫn nhận việc chăm sóc"
        assert not [t for t in tasks if t[0] == "P030" and t[1] == "dormant180"], "P030 đã từ chối tiếp thị"
        assert not [j for j in await crm_jobs(loop) if "P030" in j.name]
        assert loop.bot.sent == []


async def _tasks(loop: Loop) -> set[tuple[str, str]]:
    from sqlalchemy import text

    async with loop.api.db.session(loop.clinic_id) as session:
        rows = await session.execute(
            text(
                "SELECT p.code, t.rule_key FROM clinic.crm_task t JOIN clinic.patient p "
                "ON p.id = t.patient_id AND p.clinic_id = t.clinic_id WHERE t.status = 'open'"
            )
        )
    return {(str(code), str(rule)) for code, rule in rows.all()}
