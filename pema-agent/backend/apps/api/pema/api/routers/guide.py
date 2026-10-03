"""Staff guide and "Hoi Pema" (package U, step U7): articles of the knowledge base tagged ``guide``.

Thin routes over ``pema.clinic.actions.guide``. Reading needs ``kb.read`` (every staff role), tagging needs
``kb.manage``; the article text itself is edited in ``/admin/kb``.
"""

from __future__ import annotations

from fastapi import APIRouter, Security

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.clinic.actions import guide
from pema_contracts.guide import (
    GuideArticle,
    GuideArticleSummary,
    GuideAskRequest,
    GuideAskResponse,
    GuideTagsUpdate,
)

router = APIRouter(
    prefix="/guide",
    tags=["guide"],
    responses=ERROR_RESPONSES,
    dependencies=[Security(cookie_scheme)],
)


@router.get("/articles", response_model=list[GuideArticleSummary], summary="Guide articles (KB tag 'guide')")
async def list_articles(db: Database, ctx: Ctx) -> list[GuideArticleSummary]:
    return await guide.list_articles(db, ctx)


@router.get(
    "/articles/{article_id}", response_model=GuideArticle, summary="One article with its Markdown body"
)
async def get_article(article_id: str, db: Database, ctx: Ctx) -> GuideArticle:
    return await guide.get_article(db, ctx, article_id)


@router.put(
    "/articles/{article_id}/tags",
    response_model=GuideArticleSummary,
    summary="Replace the tags of a knowledge-base source (audited)",
)
async def set_article_tags(
    article_id: str, body: GuideTagsUpdate, db: Database, ctx: Ctx
) -> GuideArticleSummary:
    return await guide.set_tags(db, ctx, article_id, body)


@router.post(
    "/ask",
    response_model=GuideAskResponse,
    summary="Passages of the guide that answer a question (retrieval, nothing is generated)",
)
async def ask(body: GuideAskRequest, db: Database, ctx: Ctx) -> GuideAskResponse:
    # POST only so the question stays out of the URL (access logs); it changes nothing.
    return await guide.ask(db, ctx, body.question)
