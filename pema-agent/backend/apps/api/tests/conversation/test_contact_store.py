# ported from: src/conversation/contact-store.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring."""

from __future__ import annotations

import pytest

from pema.conversation.contact_store import ContactStoreImpl
from pema.conversation.pg_testing import ClinicEnv

pytestmark = pytest.mark.db


async def test_contact_store_upsert_creates_then_increments_count_and_last_seen(env: ClinicEnv) -> None:
    """upsert tạo contact mới, các lần sau tăng count + cập nhật last_seen"""
    contacts = ContactStoreImpl(env.db)
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-dem", "Hải")
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-dem", "Hải")

    rows = await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="u-dem")
    assert len(rows) == 1
    assert rows[0].message_count == 2
    assert rows[0].last_seen >= rows[0].first_seen


async def test_contact_store_non_empty_name_updates_empty_keeps_old(env: ClinicEnv) -> None:
    """tên mới không rỗng thì cập nhật, rỗng thì giữ tên cũ"""
    contacts = ContactStoreImpl(env.db)
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-ten", "Tên Cũ")
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-ten", "")
    rows = await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="u-ten")
    assert rows[0].display_name == "Tên Cũ"

    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-ten", "Tên Mới")
    rows = await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="u-ten")
    assert rows[0].display_name == "Tên Mới"


async def test_contact_store_empty_user_id_is_ignored(env: ClinicEnv) -> None:
    """userId rỗng bị bỏ qua (payload thiếu uidFrom)"""
    contacts = ContactStoreImpl(env.db)
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "", "Ai Đó")
    rows = await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="Ai Đó")
    assert len(rows) == 0


async def test_contact_store_same_user_id_in_another_account_is_counted_separately(env: ClinicEnv) -> None:
    """cùng user_id ở account khác được tính riêng"""
    contacts = ContactStoreImpl(env.db)
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-chung", "A")
    await contacts.record_contact_activity(env.clinic_id, "acc-2", "u-chung", "A")
    await contacts.record_contact_activity(env.clinic_id, "acc-2", "u-chung", "A")

    first = await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="u-chung")
    second = await contacts.list_contacts(env.clinic_id, account_id="acc-2", query="u-chung")
    assert first[0].message_count == 1
    assert second[0].message_count == 2


async def test_contact_store_search_by_display_name_works(env: ClinicEnv) -> None:
    """search theo tên hiển thị hoạt động"""
    contacts = ContactStoreImpl(env.db)
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-search", "Nguyễn Văn Tìm")
    rows = await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="Văn Tìm")
    assert len(rows) == 1
    assert rows[0].user_id == "u-search"


async def test_contact_store_search_treats_percent_and_underscore_literally(env: ClinicEnv) -> None:
    """(thêm) tìm kiếm không coi % và _ là ký tự đại diện: gõ '50%' chỉ ra dòng chứa '50%'"""
    contacts = ContactStoreImpl(env.db)
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-a", "giảm 50% hôm nay")
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-b", "giảm 500 hôm nay")

    rows = await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="50%")
    assert [r.user_id for r in rows] == ["u-a"]


async def test_contact_store_delete_removes_exactly_one_row_by_account_id_too(env: ClinicEnv) -> None:
    """xoaContact bỏ ĐÚNG một dòng, theo cả account_id"""
    contacts = ContactStoreImpl(env.db)
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-xoa", "Xóa Tôi")
    await contacts.record_contact_activity(env.clinic_id, "acc-2", "u-xoa", "Cùng id khác account")

    ok = await contacts.delete_contact(env.clinic_id, "acc-1", "u-xoa")
    assert ok is True
    assert len(await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="u-xoa")) == 0
    # Cùng user_id ở account khác PHẢI còn - thiếu account_id trong WHERE là xóa oan
    assert len(await contacts.list_contacts(env.clinic_id, account_id="acc-2", query="u-xoa")) == 1


async def test_contact_store_contact_reappears_after_delete_when_the_person_writes_again(
    env: ClinicEnv,
) -> None:
    """xóa xong người đó nhắn lại thì danh bạ tự hiện lại (auto-collected)"""
    contacts = ContactStoreImpl(env.db)
    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-lai", "Hải")
    await contacts.delete_contact(env.clinic_id, "acc-1", "u-lai")
    assert len(await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="u-lai")) == 0

    await contacts.record_contact_activity(env.clinic_id, "acc-1", "u-lai", "Hải")
    rows = await contacts.list_contacts(env.clinic_id, account_id="acc-1", query="u-lai")
    assert len(rows) == 1
    assert rows[0].message_count == 1, "đếm lại từ đầu sau khi xóa"


async def test_contact_store_deleting_a_missing_contact_returns_false(env: ClinicEnv) -> None:
    """xóa cái không tồn tại trả false, không ném"""
    contacts = ContactStoreImpl(env.db)
    assert await contacts.delete_contact(env.clinic_id, "acc-1", "u-khong-co") is False
