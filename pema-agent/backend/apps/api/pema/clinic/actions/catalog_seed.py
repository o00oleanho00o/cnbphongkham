# ported from: prototype/shared/operations-data.js (seed: rooms, services, the laser room block) and
# prototype/finance_server.py (seed: price, rate, basis)
"""Synthetic catalog for the demo clinic: four rooms, four services with their commission terms, the laser-co2
protocol and one room block. EVERYTHING here is fictional (AGENT.md); it is the prototype's sample catalog,
not the clinic's real price list (the owner supplies that: open item of PLAN-AI01-U section 6).

``seed_default_catalog`` is idempotent: when the clinic already has a service it does nothing. The protocol
row ``laser-co2`` is created by the migration; it is created here only when it is missing (a test database is
emptied between tests).
"""

from __future__ import annotations

from datetime import date, time
from typing import Final
from uuid import UUID, uuid5

from sqlalchemy import select

from pema.clinic import audit
from pema.clinic.models import Protocol, Room, RoomBlock, Service, ServiceVersion
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext

_NAMESPACE: Final = UUID("6f1c2b0e-0000-4000-8000-00000000b4a4")

ROOMS: Final[tuple[str, ...]] = ("Khám da liễu", "Tư vấn chuyên sâu", "Laser & thủ thuật", "Chăm sóc da")

# code, name, price VND, rate bp, duration, buffer, room index list, protocol
SERVICES: Final[tuple[tuple[str, str, int, int, int, int, tuple[int, ...], str | None], ...]] = (
    ("follow-up-visit", "Tái khám & đánh giá", 300_000, 1000, 30, 0, (0, 1), None),
    ("dermatology-consult", "Tư vấn da liễu", 500_000, 1500, 45, 15, (0, 1), None),
    ("laser-co2", "Laser theo chỉ định", 2_500_000, 2000, 45, 15, (2,), "laser-co2"),
    ("skin-care", "Chăm sóc theo chỉ định", 1_200_000, 1200, 45, 15, (3,), None),
)

BLOCK_DAY: Final = date(2026, 9, 21)


def demo_room_id(clinic_id: UUID, index: int) -> UUID:
    return uuid5(_NAMESPACE, f"room:{clinic_id}:{index}")


async def seed_default_catalog(db: ClinicDatabase, ctx: ActionContext) -> bool:
    """Add the sample rooms, services, protocol and block; False when the catalog already has services."""
    async with db.session() as session:
        existing = await session.scalar(select(Service.id).where(Service.clinic_id == ctx.clinic_id).limit(1))
        if existing is not None:
            return False
        has_protocol = await session.scalar(
            select(Protocol.id).where(Protocol.clinic_id == ctx.clinic_id, Protocol.code == "laser-co2")
        )
        if has_protocol is None:
            session.add(
                Protocol(
                    clinic_id=ctx.clinic_id,
                    code="laser-co2",
                    name="Laser CO2",
                    milestones=[
                        {"rule_key": "d1", "day": 1},
                        {"rule_key": "d3", "day": 3},
                        {"rule_key": "d7", "day": 7},
                    ],
                    followup_days=30,
                    window_days=45,
                )
            )
        rooms = [
            Room(id=demo_room_id(ctx.clinic_id, i), clinic_id=ctx.clinic_id, name=name)
            for i, name in enumerate(ROOMS)
        ]
        session.add_all(rooms)
        await session.flush()
        for code, name, price, rate, duration, buffer, room_index, protocol in SERVICES:
            service = Service(
                clinic_id=ctx.clinic_id,
                code=code,
                name=name,
                protocol_code=protocol,
                room_ids=[rooms[i].id for i in room_index],
            )
            session.add(service)
            await session.flush()
            session.add(
                ServiceVersion(
                    clinic_id=ctx.clinic_id,
                    service_id=service.id,
                    version_no=1,
                    price_vnd=price,
                    rate_bp=rate,
                    basis="net",
                    duration_min=duration,
                    buffer_min=buffer,
                    changed_by=ctx.actor_user_id,
                )
            )
        session.add(
            RoomBlock(
                clinic_id=ctx.clinic_id,
                room_id=rooms[2].id,
                day=BLOCK_DAY,
                starts_at=time(14, 0),
                ends_at=time(15, 0),
                reason="Bảo trì thiết bị laser",
            )
        )
        await session.flush()
        await audit.record(
            session,
            ctx,
            "seed.catalog",
            "clinic",
            ctx.clinic_id,
            {"rooms": len(ROOMS), "services": len(SERVICES)},
        )
        return True
