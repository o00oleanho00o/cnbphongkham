"""Linking a channel user (``zalo_uid``) to a patient record (PLAN-AI01 section 5, last row).

New module. In ``patient_channel`` the agent may not name a patient, an appointment or a medicine until
the Zalo user is linked to a VERIFIED patient record. Two ways to get there, both started by the patient
inside the conversation:

1. **Shares a phone number.** The number is normalised and hashed here (SHA-256 of the national format
   ``0xxxxxxxxx``); only the HASH goes to the database, which compares it with the same hash of
   ``clinic.patient.phone`` and answers ``candidate_created`` when exactly one patient matches. That is
   NOT verification: anybody who knows a phone number could claim it, so the link stays ``pending`` and a
   staff member confirms it (``POST /admin/policy/identity/confirm``, permission ``admin.policy``). A
   phone matching several patients (a family number) is ``ambiguous`` and also goes to a human.
2. **Types a code from reception.** Reception issues a one-time code for ONE patient (``issue_link_code``
   in ``pema.policy.identity_admin``), hands it over in the clinic, and the patient types it into the
   chat. Redeeming it verifies the link at once (the staff member who issued it is the verifier), then
   the code is spent. Codes expire (30 minutes) and only their hash is stored.

Both paths count failed attempts per (channel, user) in the database and answer ``rate_limited`` after
five failures in an hour, so a code or a phone number cannot be guessed through the chat.

This module holds the pure helpers (normalise, hash, extract from free text, generate a code) and
``IdentityLinker``, which the ``before_llm`` hook calls with the patient's message. It never logs a phone
number, a hash or a code.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from uuid import UUID

from pema.policy.gateway import LinkOutcome, LinkResult, PolicyGateway
from pema.policy.pii import extract_vn_phones, normalize_vn_phone
from pema.policy.text_normalize import fold_text, to_nfc
from pema_contracts.channel import ChannelKind

LINK_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
"""31 symbols, no ``0 O 1 I L``: a code read aloud or copied from paper survives."""
LINK_CODE_LENGTH = 8
LINK_CODE_TTL_MINUTES = 30
MAX_FAILED_LINK_ATTEMPTS_PER_HOUR = 5
"""Enforced by the SQL functions; repeated here so a test can check both sides agree."""


def phone_hash(raw: str) -> str | None:
    """SHA-256 hex of the national-format phone number, or ``None`` if ``raw`` is not a VN phone."""
    national = normalize_vn_phone(raw)
    if national is None:
        return None
    return hashlib.sha256(national.encode("utf-8")).hexdigest()


def generate_link_code() -> str:
    """A fresh code such as ``K7QM4XNR`` (shown to the patient as ``K7QM-4XNR``)."""
    return "".join(secrets.choice(LINK_CODE_ALPHABET) for _ in range(LINK_CODE_LENGTH))


def format_link_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def normalize_link_code(raw: str) -> str | None:
    cleaned = re.sub(r"[\s\-_.]", "", raw).upper()
    if len(cleaned) != LINK_CODE_LENGTH or any(ch not in LINK_CODE_ALPHABET for ch in cleaned):
        return None
    return cleaned


def link_code_hash(code: str) -> str | None:
    normalized = normalize_link_code(code)
    if normalized is None:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


_CODE_KEYWORD = re.compile(
    r"(?<![a-z])(?:ma|code|xac\s*(?:minh|nhan|thuc))(?![a-z])"
    r"(?:[\s:\-=]+(?:xac|minh|nhan|thuc|cua|em|toi|la|duoc|do|le|tan|dua|gui|cap|ban|nay|sau))*"
    r"[\s:\-=]*(?P<code>[A-Za-z0-9]{4}[\s\-_.]?[A-Za-z0-9]{4})(?![A-Za-z0-9])"
)
_BARE_CODE = re.compile(r"^\W*(?P<code>[A-Za-z0-9]{4}[\s\-_.]?[A-Za-z0-9]{4})\W*$")


def extract_link_code(text: str) -> str | None:
    """A link code the patient typed: after a keyword ("mã", "code", "xác minh") or as the whole message.

    A bare 8-character word elsewhere in a sentence is NOT taken for a code (it would burn an attempt on
    every ordinary message)."""
    original = to_nfc(text)
    folded = fold_text(original)
    for m in _CODE_KEYWORD.finditer(folded):
        normalized = normalize_link_code(original[m.start("code") : m.end("code")])
        if normalized is not None:
            return normalized
    bare = _BARE_CODE.match(original.strip())
    if bare is not None:
        return normalize_link_code(bare.group("code"))
    return None


@dataclass(frozen=True)
class LinkAttempt:
    """What happened to a patient message in the identity flow. Codes only; no phone, hash or code."""

    method: str
    outcome: LinkOutcome
    patient_id: UUID | None = None
    patient_code: str | None = None


class IdentityLinker:
    """Looks for a code or a phone number in the patient's text and asks the database to link them."""

    def __init__(self, gateway: PolicyGateway) -> None:
        self._gateway = gateway

    async def attempt(
        self, clinic_id: UUID, channel: ChannelKind, external_user_id: str, texts: list[str]
    ) -> LinkAttempt | None:
        """At most ONE attempt per call (a code wins over a phone number): the turn must not become an
        oracle that tries every number in a pasted list."""
        for text in texts:
            code = extract_link_code(text)
            if code is not None:
                digest = link_code_hash(code)
                if digest is not None:
                    result = await self._gateway.redeem_link_code(
                        clinic_id, channel, external_user_id, digest
                    )
                    return _attempt("code", result)
        for text in texts:
            phones = extract_vn_phones(text)
            if phones:
                digest = phone_hash(phones[0])
                if digest is not None:
                    result = await self._gateway.link_by_phone_hash(
                        clinic_id, channel, external_user_id, digest
                    )
                    return _attempt("phone", result)
        return None


def _attempt(method: str, result: LinkResult) -> LinkAttempt:
    return LinkAttempt(
        method=method, outcome=result.outcome, patient_id=result.patient_id, patient_code=result.patient_code
    )
