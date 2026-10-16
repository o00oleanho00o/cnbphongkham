"""The staff guide ("Huong dan") and "Hoi Pema" (package U, step U7).

The old Clinic Web guide (``prototype/shared/guide.js``) was a fixed array of articles with a topic list and a
search box. Here an article is a row of ``clinic.guide_article`` whose ``tags`` hold ``guide``; its body is
Markdown. Everybody with ``kb.read`` reads; ``kb.manage`` sets the tags. The articles come from the seed
(``seed_guide``); the agent never sees them (``.claude/rules/agent-crm-boundary.md``).

``ask`` is a retrieval over the passages of the articles (BM25, folded Vietnamese words); no model is called
and nothing is generated.
"""

from __future__ import annotations

from typing import Any, Final

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
"""A guide is a few dozen articles; the ceiling only keeps a huge table from loading it all."""
HEAD_CHARS: Final = 6000
"""How much of an article the list reads (enough for the summary)."""
BODY_MAX: Final = 200_000
ASK_BODY_CHARS: Final = 60_000
ASK_HITS: Final = 5


def _topic(tags: list[str]) -> str:
    return next((t for t in tags if t != GUIDE_TAG), "")


def _summary_row(row: Any) -> GuideArticleSummary:
    tags = [str(t) for t in row["tags"]]
    return GuideArticleSummary(
        id=str(row["id"]),
        title=str(row["title"]),
        topic=_topic(tags),
        tags=tags,
        summary=summary_of(str(row["body"])),
        status=KbSourceStatus.READY,  # the field stays for the web; an article here is always readable
        updated_at=row["updated_at"],
    )


async def _articles(db: ClinicDatabase, ctx: ActionContext, *, head: int) -> list[Any]:
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT id, title, tags, updated_at, left(body, :n) AS body "
                "FROM clinic.guide_article "
                "WHERE clinic_id = :c AND tags @> ARRAY['guide']::text[] "
                "ORDER BY title, id LIMIT :limit"
            ),
            {"c": ctx.clinic_id, "n": head, "limit": LIST_LIMIT},
        )
        return list(result.mappings().all())


async def list_articles(db: ClinicDatabase, ctx: ActionContext) -> list[GuideArticleSummary]:
    require(ctx, Permission.KB_READ)
    return [_summary_row(row) for row in await _articles(db, ctx, head=HEAD_CHARS)]


async def get_article(db: ClinicDatabase, ctx: ActionContext, article_id: str) -> GuideArticle:
    require(ctx, Permission.KB_READ)
    async with db.session() as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT id, title, tags, updated_at, left(body, :n) AS body "
                        "FROM clinic.guide_article "
                        "WHERE clinic_id = :c AND id = :id AND tags @> ARRAY['guide']::text[]"
                    ),
                    {"c": ctx.clinic_id, "id": article_id, "n": BODY_MAX},
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise not_found("bài hướng dẫn")
    return GuideArticle(**_summary_row(row).model_dump(), body=str(row["body"]))


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
    """Replace the tags of an article (``guide`` among them shows it, removing it hides it)."""
    require(ctx, Permission.KB_MANAGE)
    tags = normalized_tags(list(payload.tags))
    if len(tags) > 10:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Tối đa 10 nhãn cho một bài.")
    async with db.session() as session:
        row = (
            (
                await session.execute(
                    text(
                        "UPDATE clinic.guide_article SET tags = CAST(:tags AS text[]) "
                        "WHERE clinic_id = :c AND id = :id "
                        "RETURNING id, title, tags, updated_at, left(body, :n) AS body"
                    ),
                    {"c": ctx.clinic_id, "id": article_id, "tags": tags, "n": HEAD_CHARS},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise not_found("bài hướng dẫn")
        await audit.record(session, ctx, "guide.tags", "guide_article", article_id, {"tags": tags})
        return _summary_row(row)


async def ask(db: ClinicDatabase, ctx: ActionContext, question: str) -> GuideAskResponse:
    """Passages of the guide that answer ``question``, best first (at most ``ASK_HITS``)."""
    require(ctx, Permission.KB_READ)
    words = question_words(question)
    if not words:
        return GuideAskResponse(hits=[])
    flat: list[tuple[str, str, Passage]] = []
    for row in await _articles(db, ctx, head=ASK_BODY_CHARS):
        for passage in split_passages(str(row["body"])):
            flat.append((str(row["id"]), str(row["title"]), passage))
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
