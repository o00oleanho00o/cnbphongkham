"""Runs the dermatology CSKH eval cases (``pema-agent/evals/clinic_cases.json``) against the policy hooks.

New test module. Deterministic runner with a FAKE model (CI). The same file can be run by package D1's
runner against a real model; here the model is a ``FakeTextGenerator`` that counts its calls, so
"the model was not called" is a measurement, not an assumption.

The cases are fictional and their wording is a draft for the clinic's doctor (open item).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, cast
from uuid import uuid4

import pytest

from pema.policy.gateway import ApprovedTemplate, PatientPolicyFlags
from pema.policy.identity import link_code_hash, phone_hash
from pema.policy.testing import FAKE_PATIENT_ID, FakePolicyGateway, make_hooks, make_policy_context
from pema.policy.turn_guard import run_guarded_turn
from pema_contracts.channel import ChannelKind
from pema_contracts.clinic_actions import IdentityLink, IdentityLinkStatus
from pema_contracts.policy import MemorySource, PolicyProfileKey
from pema_contracts.scheduler import CreateScheduledJobInput, JobKind, OnceSchedule
from pema_contracts.testing import FAKE_CLINIC_ID, FakeTextGenerator, make_inbound

EVALS_DIR = Path(__file__).resolve().parents[5] / "evals"


class _Case(Protocol):
    id: str
    group: str
    reason: str
    profile: str
    kind: str
    input: dict[str, Any]
    expect: dict[str, Any]


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("eval_cases_clinic", EVALS_DIR / "eval_cases_clinic.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()
CASES = cast("list[_Case]", _MODULE.load_clinic_cases())
UID = "zu-1"


def _gateway(case: _Case) -> FakePolicyGateway:
    gw = FakePolicyGateway()
    flags = case.input.get("patient", {})
    gw.add_patient(
        PatientPolicyFlags(
            patient_id=FAKE_PATIENT_ID,
            code="P025",
            full_name="Nguyễn Thị Hoa",
            marketing_opt_out=bool(flags.get("marketing_opt_out", False)),
            consent_messaging=True,
            consent_marketing=True,
        )
    )
    for key, marketing in case.input.get("templates", {}).items():
        gw.templates[key] = ApprovedTemplate(key, marketing=bool(marketing))
    setup: Mapping[str, str] = case.input.get("setup", {})
    if "phone_on_file" in setup:
        digest = phone_hash(setup["phone_on_file"])
        assert digest is not None
        gw.phone_index[digest] = [FAKE_PATIENT_ID]
    if "reception_code" in setup:
        digest = link_code_hash(setup["reception_code"])
        assert digest is not None
        gw.codes[digest] = FAKE_PATIENT_ID
    return gw


async def _run_turn(case: _Case) -> None:
    profile = PolicyProfileKey(case.profile)
    verified = bool(case.input.get("identity_verified", False))
    ctx = make_policy_context(
        profile, identity_verified=verified, patient_id=FAKE_PATIENT_ID if verified else None
    )
    gw = _gateway(case)
    hooks, actions, _ = make_hooks(gateway=gw, mask_when_optional=False)
    reply = str(case.input.get("model_reply", "Dạ em chào mình ạ"))
    generator = FakeTextGenerator(reply=lambda _prompt: reply)

    async def model(prompt: str) -> str:
        return (await generator.generate_text(prompt)).text

    batch = [
        make_inbound(
            str(m.get("text", "")),
            msg_id=f"m{i}",
            update_id=f"u{i}",
            sender_id=UID,
            **({"kind": m["kind"]} if "kind" in m else {}),
            **({"sender_name": m["sender_name"]} if "sender_name" in m else {}),
        )
        for i, m in enumerate(case.input["messages"])
    ]
    turn = await run_guarded_turn(hooks, ctx, batch, model)
    expect = case.expect

    assert turn.handed_off is expect["handed_off"], case.id
    assert (len(generator.prompts) > 0) is expect["model_called"], case.id
    if "hand_off_reason" in expect:
        assert turn.hand_off_reason == expect["hand_off_reason"], case.id
    if "red_flags" in expect:
        assert list(turn.red_flags) == expect["red_flags"], case.id
    if "review_kinds" in expect:
        assert {i.kind.value for i in actions.review_items} == set(expect["review_kinds"]), case.id
    if "review_count" in expect:
        assert len(actions.review_items) == expect["review_count"], case.id
    if "outbound" in expect:
        assert turn.outbound is not None, case.id
        assert turn.outbound.action.value == expect["outbound"], case.id
    seen = generator.prompts[0] if generator.prompts else ""
    for needle in expect.get("model_input_must_contain", []):
        assert needle in seen, f"{case.id}: model input lacks {needle!r}"
    for needle in expect.get("model_input_must_not_contain", []):
        assert needle not in seen, f"{case.id}: model input leaks {needle!r}"
    for needle in expect.get("reply_must_contain", []):
        assert needle in (turn.reply or ""), f"{case.id}: reply lacks {needle!r}"
    for needle in expect.get("reply_must_not_contain", []):
        assert needle not in (turn.reply or ""), f"{case.id}: reply leaks {needle!r}"
    if "identity_after" in expect:
        key = (ChannelKind.ZALO_BOT, UID)
        state = "verified" if key in gw.verified else "pending" if key in gw.pending else "none"
        assert state == expect["identity_after"], case.id


async def _run_tools(case: _Case) -> None:
    hooks, _, _ = make_hooks()
    keys = frozenset(case.input["keys"])
    kept = await hooks.filter_tool_keys(make_policy_context(PolicyProfileKey(case.profile)), keys)
    assert sorted(keys - kept) == sorted(case.expect["removed"]), case.id
    assert sorted(kept) == sorted(case.expect["kept"]), case.id


async def _run_memory(case: _Case) -> None:
    hooks, _, _ = make_hooks()
    ctx = make_policy_context(PolicyProfileKey(case.profile))
    allowed = await hooks.allow_memory_write(ctx, MemorySource(case.input["source"]))
    assert allowed is case.expect["allowed"], case.id


async def _run_job(case: _Case) -> None:
    hooks, _, _ = make_hooks(gateway=_gateway(case))
    job = CreateScheduledJobInput.model_validate(
        {
            "clinic_id": FAKE_CLINIC_ID,
            "account_id": "acc-1",
            "thread_id": "thread-1",
            "thread_type": 0,
            "name": case.input.get("name", "Nhắc khách"),
            "kind": JobKind(case.input["job_kind"]),
            "payload": case.input["payload"],
            "schedule": OnceSchedule(run_at_utc="2026-09-21T02:00:00Z"),
            "created_by": "crm_rule",
            "patient_id": FAKE_PATIENT_ID,
        }
    )
    decision = await hooks.check_job(make_policy_context(PolicyProfileKey(case.profile)), job)
    assert decision.action.value == case.expect["action"], case.id
    if "reason" in case.expect:
        assert decision.reason == case.expect["reason"], case.id


async def _run_identity(case: _Case) -> None:
    hooks, actions, _ = make_hooks()
    status = IdentityLinkStatus(case.input["link_status"])
    actions.links[(ChannelKind.ZALO_BOT, UID)] = IdentityLink(
        channel=ChannelKind.ZALO_BOT,
        external_user_id=UID,
        status=status,
        patient_id=uuid4() if status in (IdentityLinkStatus.VERIFIED, IdentityLinkStatus.PENDING) else None,
    )
    result = await hooks.verify_identity(
        make_policy_context(PolicyProfileKey(case.profile)), ChannelKind.ZALO_BOT, UID
    )
    assert result.verified is case.expect["verified"], case.id
    assert result.needs_staff_confirmation is case.expect["needs_staff_confirmation"], case.id


async def _run_cap(case: _Case) -> None:
    hooks, _, _ = make_hooks()
    profile = PolicyProfileKey(case.profile)
    patient = FAKE_PATIENT_ID if case.input["patient_known"] else None
    a = await hooks.proactive_cap(make_policy_context(profile, thread_id="t1", patient_id=patient), 10)
    b = await hooks.proactive_cap(make_policy_context(profile, thread_id="t2", patient_id=patient), 10)
    assert a.scope_key.startswith(case.expect["scope_prefix"]), case.id
    assert (a.scope_key == b.scope_key) is case.expect["same_across_threads"], case.id


RUNNERS = {
    "turn": _run_turn,
    "tools": _run_tools,
    "memory": _run_memory,
    "job": _run_job,
    "identity": _run_identity,
    "cap": _run_cap,
}


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_clinic_eval_case(case: _Case) -> None:
    """kịch bản eval lâm sàng CSKH da liễu (hư cấu) chạy với LLM giả"""
    await RUNNERS[case.kind](case)


def test_every_case_says_why_it_exists_and_the_set_covers_the_plan_rows() -> None:
    """mỗi case có lý do tồn tại; bộ case phủ các hàng của bảng mục 5"""
    assert all(c.reason.strip() for c in CASES)
    groups = {c.group for c in CASES}
    assert {"red_flag", "media", "pii", "outbound", "identity", "tools", "memory", "jobs", "cap"} <= groups
    red_flag_categories = {f for c in CASES for f in c.expect.get("red_flags", [])}
    assert {"bleeding", "fever", "pus", "dyspnea"} <= red_flag_categories
    assert sum(1 for c in CASES if c.group == "staff_parity") >= 5


def test_the_model_is_never_expected_to_run_for_a_red_flag_case() -> None:
    """mọi case cờ đỏ phải khẳng định LLM không được gọi (trừ case phủ định/đời thường)"""
    for case in CASES:
        if case.kind == "turn" and case.expect.get("red_flags"):
            assert case.expect["model_called"] is False, case.id
