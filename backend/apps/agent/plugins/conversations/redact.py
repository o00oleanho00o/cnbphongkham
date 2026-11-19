"""Hiding who a conversation is about, so a customer's words can be shown to another customer's question.

Everything that points at a person goes: phone numbers, citizen ids, long digit strings (bank cards), emails,
links, street addresses, and the names heard in the conversation (the writers' display names, and the names
that follow "anh", "chị", "em" and the like). What is left is the shape of the exchange: what was asked and
how the staff answered. This is a safety net, not a promise: a name nobody addressed or wrote as a display
name can slip through, which is why scenarios are only ever shown to the agent, never to a customer."""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Final

PHONE: Final = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.-]?\d){8,10}(?!\d)")
CITIZEN_ID: Final = re.compile(r"(?<!\d)\d{12}(?!\d)")
LONG_NUMBER: Final = re.compile(r"(?<!\d)\d(?:[\s-]?\d){9,}(?!\d)")
EMAIL: Final = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LINK: Final = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PLACE_WORDS: Final = "đường|phố|ngõ|ngách|hẻm|kiệt|phường|xã|quận|huyện|thôn|xóm|khu phố|tổ dân phố|chung cư"
ADDRESS: Final = re.compile(
    r"(?:\b\d+[A-Za-z]?(?:/\d+[A-Za-z]?)*\s+)?"
    rf"\b(?:{PLACE_WORDS})\s+"
    rf"[\wÀ-ỹ]+(?:\s+(?!(?:{PLACE_WORDS})\b)[\wÀ-ỹ]+){{0,2}}",
    re.IGNORECASE,
)
HONORIFICS: Final = "anh|chị|em|cô|chú|bác|ông|bà|bạn|cháu|mẹ|ba|bố|dì|cậu|mợ|thím"
MIN_NAME_CHARS: Final = 2

PHONE_MARK: Final = "[số điện thoại]"
ID_MARK: Final = "[số giấy tờ]"
NUMBER_MARK: Final = "[dãy số]"
EMAIL_MARK: Final = "[email]"
LINK_MARK: Final = "[liên kết]"
ADDRESS_MARK: Final = "[địa chỉ]"
NAME_MARK: Final = "[tên]"


def _name_parts(names: Collection[str]) -> list[str]:
    """Each whole name and each word of it that is long enough, longest first (a name inside a name must not
    be cut before the whole one is)."""
    found = {part.strip() for name in names for part in (name, *name.split())}
    return sorted((p for p in found if len(p) >= MIN_NAME_CHARS), key=len, reverse=True)


def mask(text: str, names: Collection[str] = ()) -> str:
    """The text with personal details replaced by a mark."""
    masked = LINK.sub(LINK_MARK, text)
    masked = EMAIL.sub(EMAIL_MARK, masked)
    masked = CITIZEN_ID.sub(ID_MARK, masked)
    masked = PHONE.sub(PHONE_MARK, masked)
    masked = LONG_NUMBER.sub(NUMBER_MARK, masked)
    masked = ADDRESS.sub(ADDRESS_MARK, masked)
    parts = _name_parts(names)
    if not parts:
        return masked
    alternatives = "|".join(re.escape(part) for part in parts)
    # a whole display name is hidden wherever it appears; a single word of it only after an honorific, so the
    # name "Mai" does not take "ngày mai" with it
    whole = {name.strip() for name in names if len(name.strip().split()) > 1}
    for name in sorted(whole, key=len, reverse=True):
        masked = re.sub(re.escape(name), NAME_MARK, masked, flags=re.IGNORECASE)
    return re.sub(
        rf"\b({HONORIFICS})(\s+)(?:{alternatives})\b", rf"\1\2{NAME_MARK}", masked, flags=re.IGNORECASE
    )
