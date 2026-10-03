"""The staff guide ("Huong dan") and "Hoi Pema", served from the knowledge base (package U, step U7).

New module. The old Clinic Web guide (``prototype/shared/guide.js``) was a fixed array of articles with a
topic list and a search box. Here an article is a TEXT source of ``agent.kb_document`` that carries the tag
``guide``; its body is the Markdown of the source. Everybody with ``kb.read`` reads; ``kb.manage`` sets the
tags and edits the source in ``/admin/kb`` (the guide itself is read only). The guide never touches the
agents' bindings: a source an agent may read is decided there, default-deny, exactly as before.

Why raw SQL: ``agent.kb_document`` has no ORM model (the knowledge store of package D3 uses SQL). Tags are
labels, never patient data; the audit row of a tag change carries the tags and the source id only.

``ask`` is a retrieval over the passages of the guide articles (BM25, folded Vietnamese words); no model is
called and nothing is generated.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

from sqlalchemy import text

from pema.clinic import audit
from pema.clinic.actions._common import not_found
from pema.clinic.actions.guide_text import (
    PASSAGE_MAX,
    Passage,
    question_words,
    rank,
    split_passages,
    summary_of,
)
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.guide import (
    GUIDE_TAG,
    GuideArticle,
    GuideArticleSummary,
    GuideAskHit,
    GuideAskResponse,
    GuideTagsUpdate,
)
from pema_contracts.knowledge import KbSourceStatus
from pema_contracts.roles import Permission

LIST_LIMIT: Final = 200
"""A guide is a few dozen articles; the ceiling only keeps one tag on a huge KB from loading it all."""
HEAD_CHARS: Final = 6000
"""How much of a text source the list reads (enough for the summary)."""
BODY_MAX: Final = 200_000
ASK_BODY_CHARS: Final = 60_000
ASK_HITS: Final = 5
# Both queries read only sources tagged ``guide`` and not failed: a failed source (``hong``) has no usable
# text and stays hidden from the guide until it is fixed.


def _topic(tags: list[str]) -> str:
    return next((t for t in tags if t != GUIDE_TAG), "")


def _file_text(chunks: list[Any]) -> str:
    """Body of a FILE source: its chunks in order; a chunk title becomes a heading."""
    parts: list[str] = []
    for chunk in chunks:
        title = str(chunk["title"]).strip()
        content = str(chunk["content"]).strip()
        parts.append(f"## {title}\n\n{content}" if title else content)
    return "\n\n".join(parts)[:BODY_MAX]


async def _chunks_by_source(session: Any, clinic_id: UUID, ids: list[str]) -> dict[str, list[Any]]:
    if not ids:
        return {}
    rows = (
        await session.execute(
            text(
                "SELECT source_id, ord, title, content FROM agent.kb_chunk "
                "WHERE clinic_id = :c AND source_id = ANY(:ids) ORDER BY source_id, ord"
            ),
            {"c": clinic_id, "ids": ids},
        )
    ).mappings()
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        grouped.setdefault(str(row["source_id"]), []).append(row)
    return grouped


def _summary_row(row: Any, body: str) -> GuideArticleSummary:
    tags = [str(t) for t in row["tags"]]
    return GuideArticleSummary(
        id=str(row["id"]),
        title=str(row["name"]),
        topic=_topic(tags),
        tags=tags,
        summary=summary_of(body),
        status=KbSourceStatus(str(row["status"])),
        updated_at=row["updated_at"],
    )


async def _articles(db: ClinicDatabase, ctx: ActionContext, *, head: int) -> list[tuple[Any, str]]:
    """Guide rows with their text (the first ``head`` characters of a text source, the chunks of a file)."""
    async with db.session() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT id, name, kind, tags, status, updated_at, left(raw_text, :n) AS body "
                        "FROM agent.kb_document WHERE clinic_id = :c "
                        "AND tags @> ARRAY['guide']::text[] AND status <> 'hong' "
                        "ORDER BY name, id LIMIT :limit"
                    ),
                    {"c": ctx.clinic_id, "n": head, "limit": LIST_LIMIT},
                )
            )
            .mappings()
            .all()
        )
        file_ids = [str(r["id"]) for r in rows if r["kind"] == "file"]
        chunks = await _chunks_by_source(session, ctx.clinic_id, file_ids)
    return [
        (r, _file_text(chunks.get(str(r["id"]), [])) if r["kind"] == "file" else str(r["body"])) for r in rows
    ]


async def list_articles(db: ClinicDatabase, ctx: ActionContext) -> list[GuideArticleSummary]:
    require(ctx, Permission.KB_READ)
    return [_summary_row(row, body) for row, body in await _articles(db, ctx, head=HEAD_CHARS)]


async def get_article(db: ClinicDatabase, ctx: ActionContext, article_id: str) -> GuideArticle:
    require(ctx, Permission.KB_READ)
    async with db.session() as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT id, name, kind, tags, status, updated_at, left(raw_text, :n) AS body "
                        "FROM agent.kb_document WHERE clinic_id = :c AND id = :id "
                        "AND tags @> ARRAY['guide']::text[] AND status <> 'hong'"
                    ),
                    {"c": ctx.clinic_id, "id": article_id, "n": BODY_MAX},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise not_found("bài hướng dẫn")
        body = str(row["body"])
        if row["kind"] == "file":
            chunks = await _chunks_by_source(session, ctx.clinic_id, [article_id])
            body = _file_text(chunks.get(article_id, []))
    summary = _summary_row(row, body)
    return GuideArticle(**summary.model_dump(), body=body)


def normalized_tags(tags: list[str]) -> list[str]:
    """Trimmed, de-duplicated, order kept; any spelling of ``guide`` is stored as ``guide``."""
    seen: dict[str, None] = {}
    for tag in tags:
        value = tag.strip()
        if not value:
            continue
        seen.setdefault(GUIDE_TAG if value.lower() == GUIDE_TAG else value, None)
    return list(seen)


async def set_tags(
    db: ClinicDatabase, ctx: ActionContext, article_id: str, payload: GuideTagsUpdate
) -> GuideArticleSummary:
    """Replace the tags of a source (``guide`` among them makes it an article, removing it hides it)."""
    require(ctx, Permission.KB_MANAGE)
    tags = normalized_tags(list(payload.tags))
    if len(tags) > 10:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Tối đa 10 nhãn cho một nguồn.")
    async with db.session() as session:
        row = (
            (
                await session.execute(
                    text(
                        "UPDATE agent.kb_document SET tags = CAST(:tags AS text[]), updated_at = now() "
                        "WHERE clinic_id = :c AND id = :id "
                        "RETURNING id, name, kind, tags, status, updated_at, left(raw_text, :n) AS body"
                    ),
                    {"c": ctx.clinic_id, "id": article_id, "tags": tags, "n": HEAD_CHARS},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise not_found("nguồn tri thức")
        await audit.record(session, ctx, "kb.tags", "kb_source", article_id, {"tags": tags})
        return _summary_row(row, str(row["body"]))


async def ask(db: ClinicDatabase, ctx: ActionContext, question: str) -> GuideAskResponse:
    """Passages of the guide that answer ``question``, best first (at most ``ASK_HITS``)."""
    require(ctx, Permission.KB_READ)
    words = question_words(question)
    if not words:
        return GuideAskResponse(hits=[])
    flat: list[tuple[str, str, Passage]] = []
    for row, body in await _articles(db, ctx, head=ASK_BODY_CHARS):
        for passage in split_passages(body):
            flat.append((str(row["id"]), str(row["name"]), passage))
    ranked = rank(
        words,
        [f"{p.heading} {p.text}" for _, _, p in flat],
        titles=[f"{title} {p.heading}" for _, title, p in flat],
    )
    hits: list[GuideAskHit] = []
    taken: set[tuple[str, str]] = set()
    for scored in ranked:
        article_id, title, passage = flat[scored.index]
        key = (article_id, passage.heading)
        if key in taken:  # one passage per section: two halves of a long section are one answer
            continue
        taken.add(key)
        hits.append(
            GuideAskHit(
                article_id=article_id,
                article_title=title,
                heading=passage.heading,
                passage=passage.text[:PASSAGE_MAX],
                score=round(scored.score, 4),
            )
        )
        if len(hits) == ASK_HITS:
            break
    return GuideAskResponse(hits=hits)
