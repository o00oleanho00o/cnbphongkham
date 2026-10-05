"""``PostgresKnowledgeStore``: the contract object (``pema_contracts.knowledge.KnowledgeStore``) over the ported
modules. New tests - the original had module-level functions and no clinic boundary, no doctor sign-off."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from pema.knowledge.kb_ingest_worker import CaiDatIngest, KbIngestWorker
from pema.knowledge.kb_test_support import KbHarness
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.knowledge import KbSourceKind, KbSourceStatus

pytestmark = pytest.mark.db

AGENT = "agent-tu-van"
CAI_DAT = CaiDatIngest(tran_lan_thu=2, co_doan_toi_da=1200, chong_lan=10, han_ms=60_000, tran_ram_mb=192)


def tao_store(kb: KbHarness, tmp_path: Path) -> PostgresKnowledgeStore:
    return PostgresKnowledgeStore(kb.db, data_dir=tmp_path)


async def test_store_text_source_never_returns_its_raw_text_and_starts_pending(
    kb: KbHarness, tmp_path: Path
) -> None:
    """nguồn gõ tay: không bao giờ trả lại toàn văn, trạng thái đầu là cho_xu_ly"""
    store = tao_store(kb, tmp_path)
    nguon = await store.create_text_source(kb.clinic_id, name="Giờ làm việc", text="8h - 21h mỗi ngày")
    assert nguon.kind is KbSourceKind.TEXT
    assert nguon.status is KbSourceStatus.PENDING
    assert nguon.raw_text == ""
    assert (await store.get_source(kb.clinic_id, nguon.id)) is not None
    assert all(s.raw_text == "" for s in await store.list_sources(kb.clinic_id))


async def test_store_rejects_blank_text_and_an_over_long_name(kb: KbHarness, tmp_path: Path) -> None:
    """nội dung rỗng và tên quá 200 ký tự bị từ chối"""
    store = tao_store(kb, tmp_path)
    with pytest.raises(DomainError) as e1:
        await store.create_text_source(kb.clinic_id, name="trống", text="   ")
    assert e1.value.code is ErrorCode.VALIDATION_FAILED
    with pytest.raises(DomainError) as e2:
        await store.create_text_source(kb.clinic_id, name="a" * 201, text="x")
    assert e2.value.code is ErrorCode.VALIDATION_FAILED
    assert await store.list_sources(kb.clinic_id) == []


async def test_store_file_source_checks_format_signature_and_writes_nothing_when_refused(
    kb: KbHarness, tmp_path: Path
) -> None:
    """file: sai định dạng/chữ ký thì từ chối và KHÔNG ghi gì xuống đĩa hay DB"""
    store = tao_store(kb, tmp_path)
    with pytest.raises(DomainError) as e1:
        await store.create_file_source(kb.clinic_id, name="virus", format="exe", data=b"MZ")
    assert e1.value.code is ErrorCode.KB_SOURCE_INVALID
    with pytest.raises(DomainError) as e2:
        await store.create_file_source(kb.clinic_id, name="gia", format="pdf", data=b"PK\x03\x04 zip")
    assert e2.value.code is ErrorCode.KB_SOURCE_INVALID
    assert await store.list_sources(kb.clinic_id) == []
    assert not (tmp_path / "kb").exists() or list((tmp_path / "kb").iterdir()) == []


async def test_store_file_source_is_stored_then_processed_by_the_worker_and_delete_removes_the_file(
    kb: KbHarness, tmp_path: Path
) -> None:
    """file hợp lệ: lưu đĩa + DB, worker xử lý xong, xóa nguồn thì file cũng mất"""
    store = tao_store(kb, tmp_path)
    nguon = await store.create_file_source(
        kb.clinic_id, name="Hướng dẫn", format="md", data="# Sau laser\n\nTránh nắng.".encode()
    )
    assert nguon.status is KbSourceStatus.PENDING
    assert (tmp_path / nguon.path).exists()

    await KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=CAI_DAT).xu_ly_mot_vong()
    sau = await store.get_source(kb.clinic_id, nguon.id)
    assert sau is not None
    assert sau.status is KbSourceStatus.READY
    assert sau.chunk_count == 1
    chunks = await store.list_chunks(kb.clinic_id, nguon.id, offset=0, limit=10)
    assert chunks[0].title == "Sau laser"

    so_doan = await store.delete_source(kb.clinic_id, nguon.id)
    assert so_doan == 1
    assert not (tmp_path / nguon.path).exists()
    with pytest.raises(DomainError) as e:
        await store.delete_source(kb.clinic_id, nguon.id)
    assert e.value.code is ErrorCode.NOT_FOUND


async def test_store_reindex_conflicts_while_processing_and_resets_the_attempts_otherwise(
    kb: KbHarness, tmp_path: Path
) -> None:
    """reindex: 409 khi đang xử lý (I6); ngược lại cấp lại lượt thử"""
    store = tao_store(kb, tmp_path)
    nguon = await store.create_text_source(kb.clinic_id, name="x", text="abc")
    kb.kb_database.execute(
        "UPDATE agent.kb_document SET status = 'dang_xu_ly', attempts = 1 WHERE id = :id", {"id": nguon.id}
    )
    with pytest.raises(DomainError) as e:
        await store.reindex_source(kb.clinic_id, nguon.id)
    assert e.value.code is ErrorCode.INVALID_STATE
    assert (await store.get_source(kb.clinic_id, nguon.id)).status is KbSourceStatus.PROCESSING  # type: ignore[union-attr]

    await store.set_status(kb.clinic_id, nguon.id, KbSourceStatus.FAILED, error="lỗi cũ")
    await store.reindex_source(kb.clinic_id, nguon.id)
    sau = await store.get_source(kb.clinic_id, nguon.id)
    assert sau is not None
    assert (sau.status, sau.attempts) == (KbSourceStatus.PENDING, 0)


async def test_store_bindings_validate_both_sides_and_replace(kb: KbHarness, tmp_path: Path) -> None:
    """gán nguồn↔agent: kiểm tra tồn tại cả hai phía, từ chối trọn gói, thay thế chứ không cộng dồn"""
    store = tao_store(kb, tmp_path)
    n1 = await store.create_text_source(kb.clinic_id, name="n1", text="1")
    n2 = await store.create_text_source(kb.clinic_id, name="n2", text="2")
    kb.kb_database.add_agent("ban-hang")

    with pytest.raises(DomainError) as e1:
        await store.set_sources_for_agent(kb.clinic_id, "agent-khong-ton-tai", [n1.id])
    assert e1.value.code is ErrorCode.VALIDATION_FAILED
    with pytest.raises(DomainError) as e2:
        await store.set_sources_for_agent(kb.clinic_id, "ban-hang", ["khong-co"])
    assert e2.value.code is ErrorCode.VALIDATION_FAILED
    assert await store.sources_of_agent(kb.clinic_id, "ban-hang") == []

    await store.set_sources_for_agent(kb.clinic_id, "ban-hang", [n1.id, n2.id])
    await store.set_sources_for_agent(kb.clinic_id, "ban-hang", [n2.id])
    assert await store.sources_of_agent(kb.clinic_id, "ban-hang") == [n2.id]
    assert await store.agents_of_source(kb.clinic_id, n2.id) == ["ban-hang"]

    with pytest.raises(DomainError) as e3:
        await store.set_agents_for_source(kb.clinic_id, "khong-co-that", ["ban-hang"])
    assert e3.value.code is ErrorCode.NOT_FOUND
    with pytest.raises(DomainError) as e4:
        await store.set_agents_for_source(kb.clinic_id, n1.id, ["ban-hang", "ma"])
    assert e4.value.code is ErrorCode.VALIDATION_FAILED
    assert await store.agents_of_source(kb.clinic_id, n1.id) == [], "không ghi phần hợp lệ khi có phần sai"

    with pytest.raises(DomainError) as e5:
        await store.set_sources_for_agent(kb.clinic_id, "ban-hang", ["x" * 65])
    assert e5.value.code is ErrorCode.VALIDATION_FAILED


async def test_store_patient_channel_agent_cites_only_doctor_approved_sources(
    kb: KbHarness, tmp_path: Path
) -> None:
    """agent patient_channel chỉ trích nguồn đã được bác sĩ duyệt; staff_assistant thì không bị chặn"""
    store = tao_store(kb, tmp_path)
    nguon = await store.create_text_source(
        kb.clinic_id, name="Chăm sóc sau laser", text="Tránh nắng và không bôi acid trong một tuần."
    )
    await KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=CAI_DAT).xu_ly_mot_vong()
    kb.kb_database.add_agent("bot-benh-nhan", policy_profile="patient_channel")
    kb.kb_database.add_agent("tro-ly-nhan-vien", policy_profile="staff_assistant")
    await store.set_sources_for_agent(kb.clinic_id, "bot-benh-nhan", [nguon.id])
    await store.set_sources_for_agent(kb.clinic_id, "tro-ly-nhan-vien", [nguon.id])

    assert await store.search(kb.clinic_id, question="tránh nắng", agent_id="bot-benh-nhan") == []
    assert len(await store.search(kb.clinic_id, question="tránh nắng", agent_id="tro-ly-nhan-vien")) == 1

    bac_si = uuid.uuid4()
    await store.set_approved(kb.clinic_id, nguon.id, True, by_user=bac_si)
    hits = await store.search(kb.clinic_id, question="tránh nắng", agent_id="bot-benh-nhan")
    assert [h.source_id for h in hits] == [nguon.id]
    duyet = await store.get_source(kb.clinic_id, nguon.id)
    assert duyet is not None
    assert duyet.approved_by_clinical_owner is True
    assert (
        kb.kb_database.scalar("SELECT approved_by FROM agent.kb_document WHERE id = :id", {"id": nguon.id})
        == bac_si
    )

    # a caller that knows the effective profile can force the strict rule on a staff agent too
    assert (
        len(
            await store.search(
                kb.clinic_id, question="tránh nắng", agent_id="tro-ly-nhan-vien", chi_da_duyet=True
            )
        )
        == 1
    )
    await store.set_approved(kb.clinic_id, nguon.id, False, by_user=bac_si)
    assert await store.search(kb.clinic_id, question="tránh nắng", agent_id="bot-benh-nhan") == []
    assert (
        kb.kb_database.scalar("SELECT approved_by FROM agent.kb_document WHERE id = :id", {"id": nguon.id})
        is None
    )
