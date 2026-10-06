# ruff: noqa: PT018
# new tests (package U, step U4)
"""Protocols as data: the milestone days of D+1/D+3/D+7, the D+30 recommendation and the 45 day window now come
from ``clinic.protocol`` (``ProtocolConfig``), and with the laser-co2 numbers the engine behaves exactly as it did
when they were constants. The pure tests need no database; the last one reads the real table."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.crm_rules.engine import run_rules
from pema.clinic.crm_rules.profile import refresh_patient
from pema.clinic.crm_rules.protocols import DEFAULT_PROTOCOLS, ProtocolConfig, protocol_for
from pema.clinic.crm_rules.records import PatientSnapshot
from pema.clinic.crm_rules.rules import DEFAULT_RULES, LASER_PROTOCOL_ID
from pema.clinic.crm_rules.sql_store import SqlCrmRuleStore
from pema.clinic.crm_rules.testing import NOW, make_patient, session
from pema.core.db import ClinicDatabase
from pema_contracts.crm import RuleKey

TODAY = date(2026, 9, 20)
LASER = LASER_PROTOCOL_ID


def _laser_yesterday() -> PatientSnapshot:
    return make_patient(
        "P025",
        last_visit=TODAY - timedelta(days=1),
        sessions=(session("s-laser", TODAY - timedelta(days=1), LASER),),
        total_sessions=5,
        completed_sessions=1,
    )


def _chain(protocols: dict[str, ProtocolConfig] | None, patient: PatientSnapshot | None = None):  # type: ignore[no-untyped-def]
    outcome = run_rules([patient or _laser_yesterday()], DEFAULT_RULES, [], NOW, protocols)
    return {
        t.rule_key: t.due_at.date()
        for t in outcome.candidates
        if t.rule_key in (RuleKey.D1, RuleKey.D3, RuleKey.D7)
    }, outcome


def test_the_built_in_laser_co2_protocol_is_the_constants_of_the_original() -> None:
    """Giao thức laser-co2 mặc định đúng các hằng số cũ: D+1/3/7, D+30, cửa sổ 45 ngày."""
    laser = DEFAULT_PROTOCOLS[LASER]
    assert dict(laser.milestones) == {RuleKey.D1: 1, RuleKey.D3: 3, RuleKey.D7: 7}
    assert (laser.followup_days, laser.window_days, laser.active) == (30, 45, True)
    assert protocol_for(None, LASER) is laser
    assert protocol_for({}, LASER) is laser, "a store with no row falls back to the default"
    assert protocol_for(None, "peel") is None and protocol_for(None, None) is None


def test_laser_co2_behaves_the_same_with_the_seeded_protocol_row_as_with_no_configuration() -> None:
    """Laser CO2 không đổi: có dòng giao thức đã seed hay không, kết quả giống hệt."""
    seeded = {
        LASER: ProtocolConfig(
            LASER,
            "Laser CO2",
            {RuleKey.D1: 1, RuleKey.D3: 3, RuleKey.D7: 7},
            followup_days=30,
            window_days=45,
        )
    }
    for patient in (
        _laser_yesterday(),
        make_patient("P1", sessions=(session("old", TODAY - timedelta(days=45), LASER),)),
        make_patient("P2", sessions=(session("older", TODAY - timedelta(days=46), LASER),)),
        make_patient("P3", sessions=(session("plain", TODAY - timedelta(days=2)),)),
    ):
        bare = run_rules([patient], DEFAULT_RULES, [], NOW)
        with_rows = run_rules([patient], DEFAULT_RULES, [], NOW, seeded)
        assert with_rows.candidates == bare.candidates
        assert with_rows.patient_updates == bare.patient_updates
    chain, outcome = _chain(None)
    assert chain == {
        RuleKey.D1: TODAY,
        RuleKey.D3: TODAY + timedelta(days=2),
        RuleKey.D7: TODAY + timedelta(days=6),
    }
    update = outcome.patient_updates[0]
    assert update.recommendation_at == TODAY - timedelta(days=1) + timedelta(days=30)
    assert update.expected_visit_reason == "Đánh giá D+30 sau Laser CO2"


def test_a_milestone_day_of_the_protocol_wins_over_the_delay_of_the_rule() -> None:
    """Ngày của mốc trong giao thức thắng ngày trễ của luật."""
    custom = {
        LASER: replace(DEFAULT_PROTOCOLS[LASER], milestones={RuleKey.D1: 2, RuleKey.D3: 5, RuleKey.D7: 10})
    }
    chain, _ = _chain(custom)
    yesterday = TODAY - timedelta(days=1)
    assert chain == {
        RuleKey.D1: yesterday + timedelta(days=2),
        RuleKey.D3: yesterday + timedelta(days=5),
        RuleKey.D7: yesterday + timedelta(days=10),
    }


def test_a_rule_without_a_milestone_keeps_its_own_delay() -> None:
    """Mốc không khai báo trong giao thức thì dùng ngày trễ của luật."""
    custom = {LASER: replace(DEFAULT_PROTOCOLS[LASER], milestones={RuleKey.D3: 9})}
    chain, _ = _chain(custom)
    yesterday = TODAY - timedelta(days=1)
    assert chain[RuleKey.D1] == yesterday + timedelta(days=1)
    assert chain[RuleKey.D3] == yesterday + timedelta(days=9)
    assert chain[RuleKey.D7] == yesterday + timedelta(days=7)


def test_the_window_and_the_review_day_are_data() -> None:
    """Cửa sổ áp dụng và ngày đánh giá lại là dữ liệu."""
    session_day = TODAY - timedelta(days=30)
    patient = make_patient("P1", sessions=(session("s", session_day, LASER),))
    short = {LASER: replace(DEFAULT_PROTOCOLS[LASER], window_days=20, followup_days=14)}
    chain, outcome = _chain(short, patient)
    assert chain == {}, "a 30 day old session is outside a 20 day window"
    assert outcome.patient_updates[0].recommendation_at == session_day + timedelta(days=14)
    assert outcome.patient_updates[0].expected_visit_reason == "Đánh giá D+14 sau Laser CO2"
    long = {LASER: replace(DEFAULT_PROTOCOLS[LASER], window_days=60)}
    assert set(_chain(long, patient)[0]) == {RuleKey.D1, RuleKey.D3, RuleKey.D7}


def test_a_protocol_without_a_review_day_or_an_inactive_one_recommends_nothing() -> None:
    """Giao thức không có ngày đánh giá, hoặc đã tắt, thì không khuyến nghị và không sinh chuỗi."""
    patient = _laser_yesterday()
    none = {LASER: replace(DEFAULT_PROTOCOLS[LASER], followup_days=None)}
    assert refresh_patient(patient, none)[1] is None
    assert set(_chain(none)[0]) == {RuleKey.D1, RuleKey.D3, RuleKey.D7}, (
        "the chain stays; only the review goes"
    )
    off = {LASER: replace(DEFAULT_PROTOCOLS[LASER], active=False)}
    chain, outcome = _chain(off)
    assert chain == {} and outcome.patient_updates == ()


def test_another_protocol_recommends_its_review_and_chains_through_a_rule_bound_to_it() -> None:
    """Giao thức khác khuyến nghị theo ngày riêng; chuỗi D+N đi theo luật gắn với giao thức đó."""
    peel = ProtocolConfig("peel", "Peel", {RuleKey.D1: 1}, followup_days=14, window_days=10)
    patient = make_patient("P1", sessions=(session("p", TODAY - timedelta(days=1), "peel"),))
    refreshed, update = refresh_patient(patient, {"peel": peel})
    assert update is not None and update.recommendation_at == TODAY + timedelta(days=13)
    assert update.expected_visit_reason == "Đánh giá D+14 sau Peel"
    assert refreshed.last_protocol_session_id == "p"
    assert refresh_patient(patient)[1] is None, "an unknown protocol recommends nothing"
    rules = tuple(replace(r, protocol="peel") if r.key is RuleKey.D1 else r for r in DEFAULT_RULES)
    outcome = run_rules([patient], rules, [], NOW, {"peel": peel})
    d1 = [t for t in outcome.candidates if t.rule_key is RuleKey.D1]
    assert [t.due_at.date() for t in d1] == [TODAY]


@pytest.mark.db
async def test_the_store_reads_the_protocol_table_and_an_edit_moves_the_next_run(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    store = SqlCrmRuleStore(db)
    await store.ensure_rules(world.clinic_id)
    data = await store.load(world.clinic_id, NOW)
    laser = data.protocols[LASER]
    assert dict(laser.milestones) == {RuleKey.D1: 1, RuleKey.D3: 3, RuleKey.D7: 7}
    assert (laser.followup_days, laser.window_days) == (30, 45)

    def due(protocols: dict[str, ProtocolConfig]) -> dict[RuleKey, date]:
        patient = next(p for p in data.patients if p.code == "P025")
        outcome = run_rules([patient], data.rules, [], NOW, protocols)
        return {
            t.rule_key: t.due_at.date()
            for t in outcome.candidates
            if t.rule_key in (RuleKey.D1, RuleKey.D3, RuleKey.D7)
        }

    before = due(dict(data.protocols))
    assert before == {
        RuleKey.D1: TODAY,
        RuleKey.D3: TODAY + timedelta(days=2),
        RuleKey.D7: TODAY + timedelta(days=6),
    }

    manager = await client_factory("manager")
    row = next(p for p in (await manager.get("/api/v1/protocols")).json() if p["code"] == LASER)
    edited = await manager.patch(
        f"/api/v1/protocols/{row['id']}",
        json={
            "version": row["version"],
            "milestones": [
                {"rule_key": "d1", "day": 2},
                {"rule_key": "d3", "day": 3},
                {"rule_key": "d7", "day": 7},
            ],
        },
    )
    assert edited.status_code == 200, edited.text
    reloaded = await store.load(world.clinic_id, NOW)
    after = due(dict(reloaded.protocols))
    assert after[RuleKey.D1] == TODAY + timedelta(days=1)
    assert after[RuleKey.D3] == before[RuleKey.D3] and after[RuleKey.D7] == before[RuleKey.D7]
