"""The staff guide and "Hoi Pema": articles are knowledge-base sources tagged ``guide`` (package U, step U7)."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.actions.seed_guide import ARTICLES, seed_guide_articles
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

OWNER, MANAGER, DOCTOR, CS, RECEPTION = "owner", "manager", "doctor.mai", "cs.maianh", "reception.lan"


def add_source(
    admin: Engine,
    world: SeedResult,
    name: str,
    *,
    tags: list[str],
    body: str = "Nội dung mẫu.",
    status: str = "san_sang",
) -> str:
    source_id = f"src-{uuid4().hex[:10]}"
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agent.kb_document "
                "(clinic_id, id, name, kind, format, raw_text, byte_size, status, tags) "
                "VALUES (:c, :id, :name, 'text', 'md', :body, 10, :status, CAST(:tags AS text[]))"
            ),
            {
                "c": world.clinic_id,
                "id": source_id,
                "name": name,
                "body": body,
                "status": status,
                "tags": tags,
            },
        )
    return source_id


async def test_the_seed_adds_three_articles_once(db: ClinicDatabase, world: SeedResult) -> None:
    first = await seed_guide_articles(db)
    second = await seed_guide_articles(db)
    assert (first, second) == (len(ARTICLES), 0)
    assert len(ARTICLES) == 3


async def test_every_staff_role_lists_the_articles_with_topic_and_summary(
    client_factory: ClientFactory, db: ClinicDatabase, world: SeedResult
) -> None:
    await seed_guide_articles(db)
    rows: list[dict[str, object]] = []
    for user in (OWNER, MANAGER, DOCTOR, CS, RECEPTION):
        client = await client_factory(user)
        response = await client.get("/api/v1/guide/articles")
        assert response.status_code == 200, (user, response.text)
        rows = response.json()
        assert len(rows) == 3
    by_title = {str(row["title"]): row for row in rows}
    assert by_title["Bắt đầu theo vai trò"]["topic"] == "Tất cả"
    assert by_title["Bắt đầu theo vai trò"]["tags"] == ["guide", "Tất cả"]
    assert str(by_title["Bắt đầu theo vai trò"]["summary"]).startswith("Biết nơi bắt đầu")
    assert "body" not in rows[0]


async def test_an_article_comes_with_its_markdown_body(
    client_factory: ClientFactory, db: ClinicDatabase, world: SeedResult
) -> None:
    await seed_guide_articles(db)
    cs = await client_factory(CS)
    article = (await cs.get("/api/v1/guide/articles/guide-cskh-viec-hom-nay")).json()
    assert article["title"] == "CSKH chủ động: xử lý việc hôm nay"
    assert "## Cách thực hiện" in article["body"]
    assert article["topic"] == "CSKH"


async def test_a_source_without_the_guide_tag_is_not_an_article(
    client_factory: ClientFactory, admin: Engine, world: SeedResult
) -> None:
    plain = add_source(admin, world, "Tài liệu thường", tags=[])
    owner = await client_factory(OWNER)
    assert (await owner.get(f"/api/v1/guide/articles/{plain}")).status_code == 404
    assert plain not in [row["id"] for row in (await owner.get("/api/v1/guide/articles")).json()]


async def test_a_failed_source_is_hidden_from_the_guide(
    client_factory: ClientFactory, admin: Engine, world: SeedResult
) -> None:
    broken = add_source(admin, world, "Bài hỏng", tags=["guide"], status="hong")
    owner = await client_factory(OWNER)
    assert (await owner.get(f"/api/v1/guide/articles/{broken}")).status_code == 404


async def test_a_manager_tags_a_source_and_it_becomes_an_article_with_an_audit_row(
    client_factory: ClientFactory, admin: Engine, world: SeedResult
) -> None:
    source = add_source(
        admin, world, "Quy trình tiếp đón", tags=[], body="Đón khách tại quầy.\n\n## Bước\n\n1. Chào khách."
    )
    manager = await client_factory(MANAGER)
    response = await manager.put(
        f"/api/v1/guide/articles/{source}/tags", json={"tags": [" Guide ", "Lễ tân", "Lễ tân"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["tags"] == ["guide", "Lễ tân"]
    assert response.json()["topic"] == "Lễ tân"
    cs = await client_factory(CS)
    assert (await cs.get(f"/api/v1/guide/articles/{source}")).status_code == 200
    with admin.begin() as conn:
        row = conn.execute(
            text("SELECT details FROM clinic.audit_log WHERE action = 'kb.tags' AND entity_id = :id"),
            {"id": source},
        ).one()
    assert row.details == {"tags": ["guide", "Lễ tân"]}


async def test_removing_the_guide_tag_hides_the_article(
    client_factory: ClientFactory, admin: Engine, world: SeedResult
) -> None:
    source = add_source(admin, world, "Bài tạm", tags=["guide"])
    owner = await client_factory(OWNER)
    await owner.put(f"/api/v1/guide/articles/{source}/tags", json={"tags": []})
    assert (await owner.get(f"/api/v1/guide/articles/{source}")).status_code == 404


@pytest.mark.parametrize("user", [CS, RECEPTION])
async def test_roles_without_kb_manage_cannot_set_tags(
    client_factory: ClientFactory, admin: Engine, world: SeedResult, user: str
) -> None:
    source = add_source(admin, world, "Bài cấm", tags=[])
    client = await client_factory(user)
    response = await client.put(f"/api/v1/guide/articles/{source}/tags", json={"tags": ["guide"]})
    assert response.status_code == 403


async def test_more_than_ten_tags_are_refused(
    client_factory: ClientFactory, admin: Engine, world: SeedResult
) -> None:
    source = add_source(admin, world, "Nhiều nhãn", tags=[])
    owner = await client_factory(OWNER)
    response = await owner.put(
        f"/api/v1/guide/articles/{source}/tags", json={"tags": [f"nhãn {i}" for i in range(11)]}
    )
    assert response.status_code == 422


async def test_a_blank_tag_is_refused(
    client_factory: ClientFactory, admin: Engine, world: SeedResult
) -> None:
    source = add_source(admin, world, "Nhãn trống", tags=[])
    owner = await client_factory(OWNER)
    response = await owner.put(f"/api/v1/guide/articles/{source}/tags", json={"tags": ["guide", "  "]})
    assert response.status_code == 422


async def test_tagging_an_unknown_source_is_not_found(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory(OWNER)
    response = await owner.put("/api/v1/guide/articles/khong-co/tags", json={"tags": ["guide"]})
    assert response.status_code == 404


async def test_a_question_finds_the_passage_that_answers_it(
    client_factory: ClientFactory, db: ClinicDatabase, world: SeedResult
) -> None:
    await seed_guide_articles(db)
    cs = await client_factory(CS)
    response = await cs.post("/api/v1/guide/ask", json={"question": "Làm sao xử lý việc CSKH hôm nay?"})
    assert response.status_code == 200, response.text
    hits = response.json()["hits"]
    assert hits
    assert hits[0]["article_id"] == "guide-cskh-viec-hom-nay"
    assert len(hits) <= 5
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True)


async def test_a_question_without_diacritics_finds_the_same_article(
    client_factory: ClientFactory, db: ClinicDatabase, world: SeedResult
) -> None:
    await seed_guide_articles(db)
    cs = await client_factory(CS)
    hits = (await cs.post("/api/v1/guide/ask", json={"question": "ghi ket qua lien he khach"})).json()["hits"]
    assert hits[0]["article_id"] == "guide-cskh-viec-hom-nay"


async def test_a_question_the_guide_cannot_answer_returns_no_passage(
    client_factory: ClientFactory, db: ClinicDatabase, world: SeedResult
) -> None:
    await seed_guide_articles(db)
    cs = await client_factory(CS)
    response = await cs.post("/api/v1/guide/ask", json={"question": "zzzqqq"})
    assert response.json() == {"hits": []}


async def test_an_empty_question_is_refused(client_factory: ClientFactory, world: SeedResult) -> None:
    cs = await client_factory(CS)
    assert (await cs.post("/api/v1/guide/ask", json={"question": ""})).status_code == 422
    assert (await cs.post("/api/v1/guide/ask", json={})).status_code == 422


async def test_the_guide_needs_a_session(app: FastAPI, world: SeedResult) -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anonymous:
        assert (await anonymous.get("/api/v1/guide/articles")).status_code == 401
        assert (await anonymous.post("/api/v1/guide/ask", json={"question": "lịch"})).status_code == 401
