"""zalo_uid <-> patient link: phone hash, reception code, the linker, rate limit (new module).

Phone numbers and codes are fictional. The SQL side of the same flow is in ``test_identity_sql.py``.
"""

from __future__ import annotations

import hashlib
import re
from uuid import UUID, uuid4

import pytest

from pema.policy.gateway import ApprovedTemplate, LinkOutcome, PatientPolicyFlags
from pema.policy.identity import (
    LINK_CODE_ALPHABET,
    LINK_CODE_LENGTH,
    MAX_FAILED_LINK_ATTEMPTS_PER_HOUR,
    IdentityLinker,
    extract_link_code,
    format_link_code,
    generate_link_code,
    link_code_hash,
    normalize_link_code,
    phone_hash,
)
from pema.policy.testing import FakePolicyGateway
from pema_contracts.channel import ChannelKind
from pema_contracts.testing import FAKE_CLINIC_ID

CH = ChannelKind.ZALO_BOT
UID = "zalo-user-1"


def test_phone_hash_is_the_sha256_of_the_national_format() -> None:
    """băm SĐT = SHA-256 của dạng 0xxxxxxxxx; các cách viết cho cùng một băm"""
    expected = hashlib.sha256(b"0901234567").hexdigest()
    for raw in ("0901234567", "090 123 4567", "+84901234567", "84 90 123 4567", "0084901234567"):
        assert phone_hash(raw) == expected
    assert phone_hash("12345") is None
    assert phone_hash("0123456789") is None


def test_generated_codes_use_the_unambiguous_alphabet() -> None:
    """mã sinh ra dài 8, chỉ dùng bảng chữ không nhầm lẫn (không 0 O 1 I L)"""
    codes = {generate_link_code() for _ in range(200)}
    assert len(codes) == 200
    for code in codes:
        assert len(code) == LINK_CODE_LENGTH
        assert all(ch in LINK_CODE_ALPHABET for ch in code)
    assert not set("01OIL") & set(LINK_CODE_ALPHABET)


def test_code_normalisation_and_hash() -> None:
    """mã nhập có gạch/dấu cách/chữ thường vẫn ra cùng băm"""
    code = "K7QM4XNR"
    assert format_link_code(code) == "K7QM-4XNR"
    for raw in ("K7QM4XNR", "k7qm-4xnr", " K7QM 4XNR ", "K7QM_4XNR"):
        assert normalize_link_code(raw) == code
        assert link_code_hash(raw) == hashlib.sha256(code.encode()).hexdigest()
    for bad in ("", "K7QM", "K7QM4XN0", "K7QM4XNRR", "K7QM-4XN!"):
        assert normalize_link_code(bad) is None
        assert link_code_hash(bad) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mã xác minh của em là K7QM-4XNR", "K7QM4XNR"),
        ("mã: k7qm4xnr", "K7QM4XNR"),
        ("code K7QM 4XNR ạ", "K7QM4XNR"),
        ("Mã lễ tân đưa là K7QM4XNR", "K7QM4XNR"),
        ("K7QM-4XNR", "K7QM4XNR"),
        ("  k7qm4xnr!  ", "K7QM4XNR"),
        ("xác minh K7QM4XNR", "K7QM4XNR"),
        ("em muốn đặt lịch laser", None),
        ("xin chào bác sĩ", None),
        ("mã giảm giá của tháng này", None),
        ("em sẽ đến vào buổi chiều", None),
        ("nghe nói LASERCO2 tốt", None),
        ("", None),
    ],
)
def test_extract_link_code(text: str, expected: str | None) -> None:
    """lấy mã xác minh khi có từ khóa hoặc cả tin chỉ là mã; chữ 8 ký tự bất kỳ không bị coi là mã"""
    assert extract_link_code(text) == expected


def _gateway_with_patient(phone: str = "0901234567") -> tuple[FakePolicyGateway, UUID]:
    gw = FakePolicyGateway()
    patient_id = uuid4()
    gw.add_patient(
        PatientPolicyFlags(
            patient_id=patient_id,
            code="P025",
            full_name="Nguyễn Thị Hoa",
            marketing_opt_out=False,
            consent_messaging=True,
            consent_marketing=False,
        )
    )
    digest = phone_hash(phone)
    assert digest is not None
    gw.phone_index[digest] = [patient_id]
    return gw, patient_id


async def test_sharing_a_phone_creates_a_pending_candidate_never_a_verified_link() -> None:
    """khách chia sẻ SĐT khớp một hồ sơ: chỉ tạo liên kết chờ nhân viên xác nhận, không tự xác minh"""
    gw, patient_id = _gateway_with_patient()
    attempt = await IdentityLinker(gw).attempt(FAKE_CLINIC_ID, CH, UID, ["số của em 090 123 4567"])
    assert attempt is not None
    assert attempt.method == "phone"
    assert attempt.outcome is LinkOutcome.CANDIDATE_CREATED
    assert attempt.patient_id == patient_id
    assert attempt.patient_code == "P025"
    assert (CH, UID) in gw.pending
    assert (CH, UID) not in gw.verified


async def test_a_phone_that_matches_nobody_is_no_match_and_counts_as_a_failure() -> None:
    """SĐT không khớp ai: no_match và tính một lần thất bại"""
    gw, _ = _gateway_with_patient()
    attempt = await IdentityLinker(gw).attempt(FAKE_CLINIC_ID, CH, UID, ["0912345678"])
    assert attempt is not None
    assert attempt.outcome is LinkOutcome.NO_MATCH
    assert gw.failures[(CH, UID)] == 1


async def test_a_phone_shared_by_two_patients_is_ambiguous_and_needs_a_human() -> None:
    """SĐT dùng chung của hai hồ sơ (số gia đình): ambiguous, không chọn bừa"""
    gw, patient_id = _gateway_with_patient()
    digest = phone_hash("0901234567")
    assert digest is not None
    gw.phone_index[digest] = [patient_id, uuid4()]
    attempt = await IdentityLinker(gw).attempt(FAKE_CLINIC_ID, CH, UID, ["0901234567"])
    assert attempt is not None
    assert attempt.outcome is LinkOutcome.AMBIGUOUS
    assert (CH, UID) not in gw.pending


async def test_reception_code_verifies_at_once_and_is_single_use() -> None:
    """mã lễ tân xác minh ngay; dùng lần hai bị từ chối"""
    gw, patient_id = _gateway_with_patient()
    digest = link_code_hash("K7QM4XNR")
    assert digest is not None
    gw.codes[digest] = patient_id
    linker = IdentityLinker(gw)
    first = await linker.attempt(FAKE_CLINIC_ID, CH, UID, ["mã xác minh là K7QM-4XNR"])
    assert first is not None
    assert first.outcome is LinkOutcome.VERIFIED
    assert first.patient_code == "P025"
    assert gw.verified[(CH, UID)] == patient_id
    second = await linker.attempt(FAKE_CLINIC_ID, CH, "another-user", ["mã K7QM4XNR"])
    assert second is not None
    assert second.outcome is LinkOutcome.INVALID_CODE


async def test_expired_and_unknown_codes_are_refused() -> None:
    """mã hết hạn hoặc không tồn tại bị từ chối"""
    gw, _ = _gateway_with_patient()
    expired = link_code_hash("AAAABBBB")
    assert expired is not None
    gw.expired_codes.add(expired)
    linker = IdentityLinker(gw)
    out = await linker.attempt(FAKE_CLINIC_ID, CH, UID, ["mã AAAA-BBBB"])
    assert out is not None
    assert out.outcome is LinkOutcome.EXPIRED_CODE
    out = await linker.attempt(FAKE_CLINIC_ID, CH, UID, ["mã CCCC-DDDD"])
    assert out is not None
    assert out.outcome is LinkOutcome.INVALID_CODE


async def test_five_failures_stop_further_attempts() -> None:
    """quá 5 lần sai thì rate_limited, kể cả khi lần sau đúng (không dò mã qua chat)"""
    gw, patient_id = _gateway_with_patient()
    linker = IdentityLinker(gw)
    for i in range(MAX_FAILED_LINK_ATTEMPTS_PER_HOUR):
        out = await linker.attempt(FAKE_CLINIC_ID, CH, UID, [f"mã AAAA-BB{i + 2}{i + 2}"])
        assert out is not None
        assert out.outcome is LinkOutcome.INVALID_CODE
    good = link_code_hash("K7QM4XNR")
    assert good is not None
    gw.codes[good] = patient_id
    blocked = await linker.attempt(FAKE_CLINIC_ID, CH, UID, ["mã K7QM4XNR"])
    assert blocked is not None
    assert blocked.outcome is LinkOutcome.RATE_LIMITED
    assert (CH, UID) not in gw.verified


async def test_only_one_attempt_per_call_and_a_code_wins_over_a_phone() -> None:
    """mỗi lượt chỉ một lần thử; có cả mã lẫn SĐT thì dùng mã"""
    gw, patient_id = _gateway_with_patient()
    digest = link_code_hash("K7QM4XNR")
    assert digest is not None
    gw.codes[digest] = patient_id
    out = await IdentityLinker(gw).attempt(
        FAKE_CLINIC_ID, CH, UID, ["sdt 0901234567", "0912345678", "mã K7QM4XNR"]
    )
    assert out is not None
    assert out.method == "code"
    assert gw.calls == ["code"]


async def test_a_pasted_list_of_phones_tries_only_the_first() -> None:
    """dán một danh sách SĐT chỉ thử số đầu tiên (không biến cuộc chat thành công cụ dò số)"""
    gw, _ = _gateway_with_patient()
    await IdentityLinker(gw).attempt(FAKE_CLINIC_ID, CH, UID, ["0912345678 0987654321 0901234567"])
    assert gw.calls == ["phone"]


async def test_ordinary_messages_make_no_attempt() -> None:
    """tin nhắn thường không kích hoạt xác minh"""
    gw, _ = _gateway_with_patient()
    out = await IdentityLinker(gw).attempt(
        FAKE_CLINIC_ID, CH, UID, ["cho em hỏi giá laser", "hẹn thứ 7 ngày 20/09/2026"]
    )
    assert out is None
    assert gw.calls == []


def test_the_linker_never_returns_the_phone_or_the_hash_or_the_code() -> None:
    """kết quả LinkAttempt chỉ mang method/outcome/mã bệnh nhân"""
    fields = {"method", "outcome", "patient_id", "patient_code"}
    from pema.policy.identity import LinkAttempt

    assert set(LinkAttempt.__dataclass_fields__) == fields
    assert re.fullmatch(r"[0-9a-f]{64}", phone_hash("0901234567") or "")


def test_template_value_object() -> None:
    """ApprovedTemplate chỉ giữ khóa và cờ marketing"""
    assert ApprovedTemplate("followup_d1", False).marketing is False
