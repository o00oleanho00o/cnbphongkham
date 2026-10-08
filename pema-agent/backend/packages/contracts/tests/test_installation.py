"""Single tenant (ST-A): the installation clinic id fills the ``clinic_id`` of the DTOs that used to ask for it."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from pema_contracts.actions import ActionContext
from pema_contracts.installation import (
    InstallationClinicNotLoadedError,
    installation_clinic_id,
    installation_clinic_id_or_none,
    reset_installation_clinic_id,
    set_installation_clinic_id,
)
from pema_contracts.review import ReviewItemCreate, ReviewKind
from pema_contracts.roles import ActorType


@pytest.fixture(autouse=True)
def _fresh_installation_id() -> Iterator[None]:
    reset_installation_clinic_id()
    yield
    reset_installation_clinic_id()


def test_installation_id_is_not_invented_when_it_was_not_loaded() -> None:
    """không có mã cài đặt thì báo lỗi, không sinh id ngẫu nhiên"""
    assert installation_clinic_id_or_none() is None
    with pytest.raises(InstallationClinicNotLoadedError):
        installation_clinic_id()
    with pytest.raises(InstallationClinicNotLoadedError):
        ActionContext(actor_type=ActorType.USER)


def test_dtos_fill_clinic_id_from_the_installation() -> None:
    """ActionContext và ReviewItemCreate tự điền clinic_id từ mã cài đặt"""
    clinic: UUID = uuid4()
    set_installation_clinic_id(clinic)
    assert installation_clinic_id() == clinic
    assert ActionContext(actor_type=ActorType.USER).clinic_id == clinic
    review = ReviewItemCreate(job_id="turn-1", kind=ReviewKind.REPLY_DRAFT)
    assert review.clinic_id == clinic


def test_an_explicit_clinic_id_still_wins() -> None:
    set_installation_clinic_id(uuid4())
    other = uuid4()
    assert ActionContext(actor_type=ActorType.USER, clinic_id=other).clinic_id == other
