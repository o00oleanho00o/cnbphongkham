# ported from: src/knowledge/kb-agent-binding.ts
"""Bind knowledge-base sources to each agent. Schema: ``agent.agent_kb_document``.

An agent with NO source bound reads EMPTY - DEFAULT-DENY. No row in the table means "nothing configured",
not "may read everything" - reversing this lets a newly created agent read every document loaded for another
agent.

Forced deviation (SQLite -> Postgres, sync -> async): see ``kb_source_store``. The table has real foreign
keys to ``agent.agents`` and ``agent.kb_document`` (``ON DELETE CASCADE``), so the manual cleanup that the
original needed when an agent or a source was deleted (``xoaGanNguonCuaAgent``) is done by the database.
Deleting the agent "Bán hàng" (id ``ban-hang``) and creating another agent with the SAME name, which gets the
SAME deterministic slug id, can therefore never inherit the old bindings - the original's "reverse the
default-deny" scenario cannot happen.

``chi_da_duyet`` is the one addition: the doctor's sign-off. A document an agent of the ``patient_channel``
profile may cite must be approved (``approved_by_clinical_owner``); see ``kb_search``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def nguon_cua_agent(
    session: AsyncSession, clinic_id: UUID, agent_id: str, *, chi_da_duyet: bool = False
) -> list[str]:
    rows = (
        await session.execute(
            text(
                "SELECT b.source_id FROM agent.agent_kb_document b "
                "JOIN agent.kb_document d ON d.clinic_id = b.clinic_id AND d.id = b.source_id "
                "WHERE b.clinic_id = :c AND b.agent_id = :a "
                "AND (NOT :chi_da_duyet OR d.approved_by_clinical_owner) "
                "ORDER BY b.source_id"
            ),
            {"c": clinic_id, "a": agent_id, "chi_da_duyet": chi_da_duyet},
        )
    ).scalars()
    return list(rows)


async def agent_cua_nguon(session: AsyncSession, clinic_id: UUID, source_id: str) -> list[str]:
    """The REVERSE direction of ``nguon_cua_agent`` - which agents have this source bound. The dashboard
    (I19) reads it BEFORE showing the delete confirmation: after the delete these agents lose access at once,
    and the dialog must state that real number instead of a generic warning that says nothing."""
    rows = (
        await session.execute(
            text(
                "SELECT agent_id FROM agent.agent_kb_document "
                "WHERE clinic_id = :c AND source_id = :s ORDER BY agent_id"
            ),
            {"c": clinic_id, "s": source_id},
        )
    ).scalars()
    return list(rows)


async def dat_nguon_cho_agent(
    session: AsyncSession, clinic_id: UUID, agent_id: str, source_ids: list[str]
) -> None:
    """RESET the whole source list of an agent - REPLACES, never accumulates. The dashboard sends the whole
    list of ticked checkboxes, not a list of additions/removals. Duplicates are dropped (a repeated id would
    make the second INSERT fail with a UNIQUE violation in the middle of the transaction, ruining the whole
    operation for a harmless mistake that needs no blocking)."""
    id_duy_nhat = list(dict.fromkeys(source_ids))
    await session.execute(
        text("DELETE FROM agent.agent_kb_document WHERE clinic_id = :c AND agent_id = :a"),
        {"c": clinic_id, "a": agent_id},
    )
    if id_duy_nhat:
        await session.execute(
            text(
                "INSERT INTO agent.agent_kb_document (clinic_id, agent_id, source_id) "
                "SELECT :c, :a, unnest(CAST(:ids AS text[]))"
            ),
            {"c": clinic_id, "a": agent_id, "ids": id_duy_nhat},
        )


async def dat_agent_cho_nguon(
    session: AsyncSession, clinic_id: UUID, source_id: str, agent_ids: list[str]
) -> None:
    """RESET the list of agents that may read ONE source - the reverse of ``dat_nguon_cho_agent``, for the
    binding done right on the Knowledge base page.

    Why this direction is needed although the other exists: the person who loads a document thinks "who may
    read this document", not "what can this agent read". Making them remember the source name and go to the
    Agents page to find the right agent is exactly where real users got lost - a source loaded and sitting
    there that no agent can read while the table still shows "Sẵn sàng".

    REPLACES and drops duplicates - same reason as ``dat_nguon_cho_agent``."""
    id_duy_nhat = list(dict.fromkeys(agent_ids))
    await session.execute(
        text("DELETE FROM agent.agent_kb_document WHERE clinic_id = :c AND source_id = :s"),
        {"c": clinic_id, "s": source_id},
    )
    if id_duy_nhat:
        await session.execute(
            text(
                "INSERT INTO agent.agent_kb_document (clinic_id, agent_id, source_id) "
                "SELECT :c, unnest(CAST(:ids AS text[])), :s"
            ),
            {"c": clinic_id, "s": source_id, "ids": id_duy_nhat},
        )


async def dem_agent_theo_nguon(session: AsyncSession, clinic_id: UUID) -> dict[str, int]:
    """Count the agents bound, for EVERY source at once - one GROUP BY instead of calling ``agent_cua_nguon``
    for each row of the table. The Knowledge base page refreshes every few seconds so an N+1 here would be an
    N+1 repeated forever.

    A source with NO agent is ABSENT from the dict (GROUP BY makes no row for an empty group) - the caller
    must read "no key" as 0, which is exactly the case that needs a warning."""
    rows = (
        await session.execute(
            text(
                "SELECT source_id, count(*) AS so FROM agent.agent_kb_document "
                "WHERE clinic_id = :c GROUP BY source_id"
            ),
            {"c": clinic_id},
        )
    ).all()
    return {r[0]: int(r[1]) for r in rows}


async def xoa_gan_nguon_cua_agent(session: AsyncSession, clinic_id: UUID, agent_id: str) -> None:
    """Clear every binding of an agent. Kept for callers that want it explicit; the database already does it
    through ``ON DELETE CASCADE`` when the agent row is deleted (see the module docstring)."""
    await session.execute(
        text("DELETE FROM agent.agent_kb_document WHERE clinic_id = :c AND agent_id = :a"),
        {"c": clinic_id, "a": agent_id},
    )


async def agent_ton_tai(session: AsyncSession, clinic_id: UUID, agent_id: str) -> bool:
    """Does the agent exist (``getAgent(agentId)`` of the route). Reads ``agent.agents``, owned by D2: a
    read-only existence check, the only thing the knowledge routes need from it."""
    row = (
        await session.execute(
            text("SELECT 1 FROM agent.agents WHERE clinic_id = :c AND id = :a"),
            {"c": clinic_id, "a": agent_id},
        )
    ).first()
    return row is not None


async def ton_tai_cac_agent(session: AsyncSession, clinic_id: UUID, agent_ids: list[str]) -> set[str]:
    """Which of ``agent_ids`` exist - one query, not one per id."""
    if not agent_ids:
        return set()
    rows = (
        await session.execute(
            text("SELECT id FROM agent.agents WHERE clinic_id = :c AND id = ANY(:ids)"),
            {"c": clinic_id, "ids": agent_ids},
        )
    ).scalars()
    return set(rows)
