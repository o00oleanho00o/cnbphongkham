"""Staff guide ("Huong dan") served from the knowledge base.

The old Clinic Web guide (``prototype/shared/guide.js``) was an array of articles. Here an article is a text
source of the knowledge base that carries the tag ``guide`` (``agent.kb_document.tags``); its body is
Markdown, its topic (the old ``role`` eyebrow) is the first other tag. Staff read; whoever holds
``kb.manage`` edits the source in ``/admin/kb`` and sets the tags (``PUT /guide/articles/{id}/tags``).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.knowledge import KbSourceStatus

GUIDE_TAG = "guide"
"""The tag that makes a knowledge-base source an article of the guide."""

type GuideTag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class GuideArticleSummary(ApiModel):
    id: str
    title: str
    topic: str = Field(description="First tag other than 'guide' (the old 'role' eyebrow); '' when none.")
    tags: list[str]
    summary: str = Field(description="First paragraph of the article, at most 240 characters.")
    status: KbSourceStatus
    updated_at: VnDatetime


class GuideArticle(GuideArticleSummary):
    body: str = Field(description="Markdown. Headings, paragraphs, lists, bold and links only.")


class GuideTagsUpdate(ApiModel):
    """Replace the tags of a source. ``guide`` in the list makes it an article; removing it hides it."""

    tags: list[GuideTag] = Field(max_length=10)


class GuideAskRequest(ApiModel):
    """The question is sent in the body, not the URL: it may name a customer and urls reach access logs."""

    question: str = Field(min_length=1, max_length=500)


class GuideAskHit(ApiModel):
    """One passage of an article that matches the question, with where it came from."""

    article_id: str
    article_title: str
    heading: str = Field(description="Heading of the section the passage is in; '' for the lead.")
    passage: str
    score: float


class GuideAskResponse(ApiModel):
    hits: list[GuideAskHit]
