"""Foundation contracts of the clinic application: roles, +07:00 time, the error envelope, strict DTOs and
the shape of a channel message (kept for the future channel integration)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from pema_contracts.channel import ChannelKind, InboundKind, InboundMessage, ThreadKind
from pema_contracts.common import VN_TZ, ApiModel, VnDatetime, now_vn
from pema_contracts.errors import ERROR_HTTP_STATUS, DomainError, ErrorCode
from pema_contracts.roles import STAFF_ROLES, Role


class _Stamp(BaseModel):
    at: VnDatetime


def test_the_roles_are_fixed_and_the_patient_is_not_staff() -> None:
    assert {r.value for r in Role} == {
        "owner",
        "manager",
        "doctor",
        "cs_staff",
        "reception",
        "accountant",
        "patient",
    }
    assert Role.PATIENT not in STAFF_ROLES


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _Stamp(at=datetime(2026, 9, 20, 9, 0, 0))


def test_datetime_is_normalised_to_plus_seven_and_serialised_with_offset() -> None:
    stamp = _Stamp(at=datetime(2026, 9, 20, 2, 0, 0, tzinfo=UTC))
    assert stamp.at.utcoffset() == timedelta(hours=7)
    assert json.loads(stamp.model_dump_json())["at"] == "2026-09-20T09:00:00+07:00"
    other_zone = _Stamp(at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone(timedelta(hours=9))))
    assert other_zone.model_dump(mode="json")["at"] == "2026-09-20T07:00:00+07:00"


def test_every_error_code_has_an_http_status() -> None:
    assert set(ERROR_HTTP_STATUS) == set(ErrorCode)
    assert ERROR_HTTP_STATUS[ErrorCode.NOT_IMPLEMENTED] == 501


def test_domain_error_maps_to_envelope() -> None:
    err = DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy.")
    body = err.to_response("req-1")
    assert err.http_status == 404
    assert body.error.code is ErrorCode.NOT_FOUND
    assert body.error.request_id == "req-1"


def test_dtos_reject_unknown_fields() -> None:
    class Probe(ApiModel):
        name: str

    with pytest.raises(ValidationError):
        Probe.model_validate({"name": "x", "surprise": 1})


def test_inbound_message_round_trips_with_plus_seven() -> None:
    msg = InboundMessage(
        channel=ChannelKind.ZALO_BOT,
        account_id="acc-1",
        update_id=uuid4().hex,
        kind=InboundKind.TEXT,
        thread_id="t-1",
        thread_kind=ThreadKind.GROUP,
        is_group=True,
        sender_id="u-1",
        text="xin chào",
        msg_id=uuid4().hex,
        sent_at=now_vn(),
    )
    data = json.loads(msg.model_dump_json())
    assert data["sent_at"].endswith("+07:00")
    assert InboundMessage.model_validate(data) == msg


def test_now_vn_is_plus_seven() -> None:
    assert now_vn().utcoffset() == VN_TZ.utcoffset(None)
