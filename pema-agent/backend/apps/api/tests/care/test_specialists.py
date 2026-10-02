"""Specialist configuration, tool resolution and the Reviewer (package M, step M4). New tests."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from pema.care.specialists.knowledge import knowledge_spec
from pema.care.specialists.reviewer import (
    CHECK_DEPTH,
    CHECK_HAS_SOURCES,
    CHECK_NO_DIAGNOSIS,
    CHECK_NO_PII,
    CHECK_TEMPLATE,
    DEFAULT_CHECKLIST,
    ReviewChecklist,
    review_draft,
    reviewer_spec,
)
from pema.care.specialists.scheduler import scheduler_spec
from pema.care.specialists.spec import (
    ALL_KNOWN_TOOL_KEYS,
    DELEGATE_TOOL,
    KNOWLEDGE_ID,
    REVIEWER_ID,
    SCHEDULER_ID,
    SPECIALIST_IDS,
    SpecialistConfigError,
    SpecialistSpec,
    inherited_profile_key,
    profile_of_turn,
)
from pema.care.specialists.store import all_specs
from pema.care.specialists.toolkit import SpecialistToolkit, ToolResolutionError
from pema_contracts.policy import PolicyProfileKey

CLINIC = UUID("00000000-0000-4000-8000-0000000000c1")


# ------------------------------------------------------------------------------------ the three records
def test_the_allowlists_are_those_of_the_plan() -> None:
    assert scheduler_spec().allowed_tools == {"appointment.search_slots", "appointment.book"}
    assert knowledge_spec().allowed_tools == {"kb_search", "kb_ingest", "kb_list"}
    assert reviewer_spec().allowed_tools == frozenset()
    assert reviewer_spec().read_only is True


def test_no_specialist_has_delegate_in_its_allowlist_but_every_record_denies_it() -> None:
    for spec in all_specs():
        assert DELEGATE_TOOL not in spec.allowed_tools
        assert DELEGATE_TOOL in spec.disabled_tools()
        record = spec.to_agent_profile(CLINIC)
        assert DELEGATE_TOOL in record.disabled_tools
        assert not set(record.disabled_tools) & spec.allowed_tools
        assert set(record.disabled_tools) | spec.allowed_tools == set(ALL_KNOWN_TOOL_KEYS)


def test_the_ids_fit_the_agent_id_rule_of_the_database() -> None:
    assert SPECIALIST_IDS == (SCHEDULER_ID, KNOWLEDGE_ID, REVIEWER_ID)
    assert all(spec.agent_id.replace("-", "").isalnum() for spec in all_specs())


def test_a_specialist_cannot_be_configured_with_delegate_or_an_unknown_tool() -> None:
    with pytest.raises(SpecialistConfigError):
        SpecialistSpec("x", "x", "x", "x", frozenset({DELEGATE_TOOL}))
    with pytest.raises(SpecialistConfigError):
        SpecialistSpec("x", "x", "x", "x", frozenset({"made_up_tool"}))
    with pytest.raises(SpecialistConfigError):
        SpecialistSpec("x", "x", "x", "x", frozenset({"kb_search"}), read_only=True)


# --------------------------------------------------------------------------------------- tool resolution
def test_resolving_delegate_for_any_specialist_fails_at_resolution_time() -> None:
    for spec in all_specs():
        with pytest.raises(ToolResolutionError):
            SpecialistToolkit.resolve_tool(spec, DELEGATE_TOOL)
    with pytest.raises(ToolResolutionError):
        SpecialistToolkit.resolve_tool(scheduler_spec(), "kb_search")
    SpecialistToolkit.resolve_tool(scheduler_spec(), "appointment.book")  # no error


def test_the_record_and_the_profile_can_only_narrow_the_allowlist() -> None:
    spec = scheduler_spec()
    record = spec.to_agent_profile(CLINIC)
    full = SpecialistToolkit.resolve_keys(spec, record, PolicyProfileKey.STAFF_ASSISTANT)
    assert full == spec.allowed_tools
    narrowed = record.model_copy(update={"disabled_tools": [*record.disabled_tools, "appointment.book"]})
    assert SpecialistToolkit.resolve_keys(spec, narrowed, PolicyProfileKey.STAFF_ASSISTANT) == {
        "appointment.search_slots"
    }
    # a record that forgot to deny a tool never widens the allowlist, nor lets delegate in
    sloppy = record.model_copy(update={"disabled_tools": []})
    assert (
        SpecialistToolkit.resolve_keys(spec, sloppy, PolicyProfileKey.STAFF_ASSISTANT) == spec.allowed_tools
    )
    assert DELEGATE_TOOL not in SpecialistToolkit.resolve_keys(spec, None, PolicyProfileKey.PATIENT_CHANNEL)


# ------------------------------------------------------------------------------------ profile inheritance
def test_the_strictest_profile_of_the_chain_wins() -> None:
    staff, patient = PolicyProfileKey.STAFF_ASSISTANT, PolicyProfileKey.PATIENT_CHANNEL
    assert inherited_profile_key(staff, staff) is staff
    assert inherited_profile_key(staff, patient) is patient
    assert inherited_profile_key() is patient


def test_toward_a_patient_the_chain_is_always_patient_channel() -> None:
    # the specialists of the plan are staff_assistant; the care agent is patient_channel
    assert {s.policy_profile for s in all_specs()} == {PolicyProfileKey.STAFF_ASSISTANT}
    assert profile_of_turn("patient_channel", all_specs()) is PolicyProfileKey.PATIENT_CHANNEL
    assert profile_of_turn("garbage-value", all_specs()) is PolicyProfileKey.PATIENT_CHANNEL


# -------------------------------------------------------------------------------------------- reviewer
async def test_a_draft_with_a_fake_phone_number_is_flagged() -> None:
    draft = "Chị liên hệ số 0901 234 567 để đổi lịch nhé."  # synthetic number
    result = await review_draft(draft, {}, DEFAULT_CHECKLIST)
    assert result.needs_human is True
    assert result.artifacts[0]["flags"] == [CHECK_NO_PII]
    detail = str(result.artifacts[0]["checks"])
    assert "phone" in detail
    assert "0901" not in detail  # the kind is reported, never the value


async def test_a_clean_draft_passes_every_evaluated_check() -> None:
    result = await review_draft(
        "Nhắc lịch hẹn của chị vào 9h sáng mai ạ.", {"action_type": "reminder_template"}, DEFAULT_CHECKLIST
    )
    assert result.needs_human is False
    assert result.confidence == 1.0
    assert result.artifacts[0]["flags"] == []


@pytest.mark.parametrize(
    "phrase", ["Theo chẩn đoán của em thì chị cần nghỉ", "Chị bị viêm rồi", "Em kê đơn thêm nhé"]
)
async def test_a_diagnosis_or_prescription_phrase_is_flagged_with_or_without_diacritics(phrase: str) -> None:
    for text in (phrase, phrase.lower().replace("ẩ", "a").replace("đ", "d")):
        result = await review_draft(text, {}, DEFAULT_CHECKLIST)
        assert CHECK_NO_DIAGNOSIS in result.artifacts[0]["flags"], text


async def test_a_kb_answer_without_a_citation_is_flagged_and_with_one_it_passes() -> None:
    context: dict[str, Any] = {"action_type": "faq_kb_answer", "citations": []}
    flagged = await review_draft("Sau nặn mụn nên tránh nắng.", context, DEFAULT_CHECKLIST)
    assert flagged.artifacts[0]["flags"] == [CHECK_HAS_SOURCES]
    ok = await review_draft(
        "Sau nặn mụn nên tránh nắng.", {**context, "citations": ["src-1"]}, DEFAULT_CHECKLIST
    )
    assert ok.needs_human is False


async def test_a_template_must_match_its_approved_body_with_variables_free() -> None:
    body = "Nhắc lịch hẹn của {ten} lúc {gio}. Phòng khám Pema."
    context = {"template_id": "reminder-1", "template_body": body}
    assert (
        await review_draft(
            "Nhắc lịch hẹn của chị lúc 9h sáng mai. Phòng khám Pema.", context, DEFAULT_CHECKLIST
        )
    ).needs_human is False
    changed = await review_draft(
        "Nhắc lịch hẹn của chị lúc 9h. Nhớ uống thuốc. Phòng khám Pema.", context, DEFAULT_CHECKLIST
    )
    assert CHECK_TEMPLATE not in changed.artifacts[0]["flags"]  # variables absorb extra words
    different = await review_draft("Chào chị, em nhắc lịch ạ.", context, DEFAULT_CHECKLIST)
    assert different.artifacts[0]["flags"] == [CHECK_TEMPLATE]
    unknown = await review_draft("Chào chị", {"template_id": "reminder-1"}, DEFAULT_CHECKLIST)
    assert unknown.artifacts[0]["flags"] == [CHECK_TEMPLATE]


async def test_the_claimed_depth_may_not_be_shallower_than_the_classified_one() -> None:
    async def classify(text: str) -> str | None:
        return "D3"

    shallow = await review_draft("x", {"claimed_depth": "D1"}, DEFAULT_CHECKLIST, classify_depth=classify)
    assert CHECK_DEPTH in shallow.artifacts[0]["flags"]
    deeper = await review_draft("x", {"claimed_depth": "D4"}, DEFAULT_CHECKLIST, classify_depth=classify)
    assert CHECK_DEPTH not in deeper.artifacts[0]["flags"]
    missing = await review_draft("x", {}, DEFAULT_CHECKLIST, classify_depth=classify)
    assert CHECK_DEPTH in missing.artifacts[0]["flags"]
    skipped = await review_draft("x", {"claimed_depth": "D1"}, DEFAULT_CHECKLIST)
    assert CHECK_DEPTH not in skipped.artifacts[0]["flags"]
    assert any(c["status"] == "skipped" for c in skipped.artifacts[0]["checks"])


async def test_a_check_can_be_switched_off_in_the_checklist_row() -> None:
    config = ReviewChecklist.from_config({"enabled": {CHECK_NO_PII: False}})
    result = await review_draft("Gọi 0901 234 567 nhé", {}, config)
    assert CHECK_NO_PII not in result.artifacts[0]["flags"]


async def test_nothing_evaluated_means_a_person_looks() -> None:
    off = ReviewChecklist.from_config(
        {
            "enabled": dict.fromkeys(
                (CHECK_HAS_SOURCES, CHECK_NO_DIAGNOSIS, CHECK_NO_PII, CHECK_TEMPLATE, CHECK_DEPTH), False
            )
        }
    )
    result = await review_draft("x", {}, off)
    assert (result.needs_human, result.confidence) == (True, 0.0)


def test_the_default_checklist_is_flagged_pending_and_a_broken_row_falls_back_to_it() -> None:
    assert DEFAULT_CHECKLIST.pending_doctor_approval is True
    broken = ReviewChecklist.from_config({"enabled": "not-a-dict"})
    assert broken == DEFAULT_CHECKLIST
    assert ReviewChecklist.from_config(None) == DEFAULT_CHECKLIST
