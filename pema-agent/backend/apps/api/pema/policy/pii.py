"""PII mask for the ``patient_channel`` profile (PLAN-AI01 section 5, principle 4).

New module (no zalo-agent original). Mandatory in ``patient_channel``: patient data must not reach a
model in clear text. It masks, BEFORE any model call:

* phone numbers (Vietnamese mobile and landline, with ``+84``/``84``/``0084``, any separator, digits
  spelled out in words, and digits typed after a keyword such as "sđt");
* national ids: 12-digit CCCD, 9-digit CMND next to a keyword like "cmnd", "căn cước";
* e-mail addresses, including "abc at gmail dot com" and "abc a còng gmail chấm com";
* specific addresses: house number + street/alley, building/floor/room, "địa chỉ ... <clause>";
  ward/district tied to a street are masked with it; a bare city name is not an address;
* dates of birth next to a keyword ("sinh ngày", "dob");
* names: the sender's channel name, the verified patient's name, and "tên là X" / "em là Nguyễn Văn A"
  self-introductions. A name becomes a reference code: the verified patient is ``[KH_P025]`` (the
  patient code), anybody else ``[NGUOI_1]``.

All matching runs on a diacritic-folded copy of the text (``text_normalize.fold_text``) that has the SAME
length as the original, so "sdt 0901..." and "sđt 0901..." are both found and the cut happens in the
real text.

Restoring is deliberately narrow ("khôi phục an toàn"): ``restore`` puts back NAMES only, and only the
ones this session minted (the verified patient's display name for ``[KH_<code>]``, what the patient typed
for ``[NGUOI_n]``). Phone, id, e-mail, address and birth date placeholders are never restored: a human
reads the original in the Inbox. A placeholder the model invented, or one that cannot be restored, is
replaced by ``[đã ẩn]`` so the reviewer sees a hole instead of a leak.

A ``MaskSession`` keeps what it needs to restore names in memory (a name is as sensitive as the text it
came from, so the ``MaskVault`` expires sessions and caps their number) and keeps only SHA-256 digests of
everything else, which is enough to give the same original the same placeholder in a thread.

Limits, stated plainly: a name typed in lower case without an introduction ("em hoa") is not recognised
unless it is a known name; a phone number split into three messages is not joined; free-text addresses
without a house number or a keyword ("nhà em ở gần chợ X") are not masked. The red-flag check and the
review queue, not this mask, are the safety net for those.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from pema.policy.text_normalize import fold_text, to_nfc


class PiiKind(StrEnum):
    PHONE = "phone"
    NATIONAL_ID = "national_id"
    EMAIL = "email"
    ADDRESS = "address"
    BIRTHDATE = "birthdate"
    NAME = "name"


LABELS: dict[PiiKind, str] = {
    PiiKind.PHONE: "SDT",
    PiiKind.NATIONAL_ID: "CCCD",
    PiiKind.EMAIL: "EMAIL",
    PiiKind.ADDRESS: "DIACHI",
    PiiKind.BIRTHDATE: "NGAYSINH",
    PiiKind.NAME: "NGUOI",
}
PATIENT_LABEL = "KH"
"""Placeholder label of the verified patient's own name: ``[KH_<patient code>]``."""

RESTORABLE_KINDS: frozenset[PiiKind] = frozenset({PiiKind.NAME})
"""The ONLY kinds ``restore`` will put back."""

HIDDEN = "[đã ẩn]"

_PRIORITY: dict[PiiKind, int] = {
    PiiKind.EMAIL: 0,
    PiiKind.PHONE: 1,
    PiiKind.NATIONAL_ID: 2,
    PiiKind.BIRTHDATE: 3,
    PiiKind.ADDRESS: 4,
    PiiKind.NAME: 5,
}

# ----------------------------------------------------------------------------- phone
_SEP = r"[\s.\-_()]{0,2}"
_PHONE_CANDIDATE = re.compile(rf"(?<!\d)(?:(?:\+|00)\s?84|84|0)(?:{_SEP}\d){{8,10}}(?!\d)")
_PHONE_KEYWORD = re.compile(
    r"(?<![a-z])(?:sdt|so\s*dt|so\s*dien\s*thoai|dien\s*thoai|phone|zalo|lien\s*he|hotline|tel|mobile|dt|lh)"
    r"(?:\s*(?:la|:|-|=|so|cua\s*em|cua\s*minh|cua\s*toi|moi|cu))*[\s:.\-]*"
    r"(?P<num>\+?\d(?:[\s.\-_()]{0,2}\d){7,13})(?!\d)"
)
_DIGIT_WORDS: dict[str, str] = {
    "khong": "0",
    "mot": "1",
    "hai": "2",
    "ba": "3",
    "bon": "4",
    "tu": "4",
    "nam": "5",
    "lam": "5",
    "sau": "6",
    "bay": "7",
    "tam": "8",
    "chin": "9",
}
_WORD_DIGITS = re.compile(
    r"(?<![a-z0-9])(?:(?:khong|mot|hai|ba|bon|tu|nam|lam|sau|bay|tam|chin|\d+)(?:[\s.,\-]+|(?![a-z0-9]))){9,}"
)
_VN_MOBILE = re.compile(r"^0[35789]\d{8}$")
_VN_LANDLINE = re.compile(r"^02\d{9}$")


def normalize_vn_phone(raw: str) -> str | None:
    """National format ``0xxxxxxxxx`` of a Vietnamese phone number, or ``None`` if it is not one."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0084"):
        digits = "0" + digits[4:]
    elif digits.startswith("84") and len(digits) in (11, 12):
        rest = digits[2:]
        digits = rest if rest.startswith("0") else "0" + rest
    if _VN_MOBILE.match(digits) or _VN_LANDLINE.match(digits):
        return digits
    return None


def _phone_matches(folded: str) -> list[tuple[int, int, str | None]]:
    """``(start, end, national number or None)``; ``None`` = looks like a phone (keyword) but is malformed."""
    found: list[tuple[int, int, str | None]] = []
    for m in _PHONE_CANDIDATE.finditer(folded):
        number = normalize_vn_phone(m.group())
        if number is not None:
            start = m.start() - 1 if m.start() > 0 and folded[m.start() - 1] == "(" else m.start()
            found.append((start, m.end(), number))
    for m in _PHONE_KEYWORD.finditer(folded):
        digits = re.sub(r"\D", "", m.group("num"))
        if len(digits) >= 8:
            found.append((*m.span("num"), normalize_vn_phone(digits)))
    for m in _WORD_DIGITS.finditer(folded):
        tokens: list[str] = re.findall(r"khong|mot|hai|ba|bon|tu|nam|lam|sau|bay|tam|chin|\d+", m.group())
        digits = "".join(_DIGIT_WORDS.get(t, t) for t in tokens)
        number = normalize_vn_phone(digits)
        if number is not None:
            found.append((m.start(), m.start() + len(m.group().rstrip(" .,-")), number))
    return found


def _phone_spans(folded: str) -> list[tuple[int, int]]:
    return [(a, b) for a, b, _ in _phone_matches(folded)]


def extract_vn_phones(text: str) -> list[str]:
    """Distinct VALID Vietnamese phone numbers in ``text``, national format, in order of appearance.

    Used by the identity flow (a patient shares a phone number); malformed digit runs are skipped."""
    folded = fold_text(to_nfc(text))
    seen: dict[str, None] = {}
    for _, _, number in sorted(_phone_matches(folded), key=lambda t: t[0]):
        if number is not None:
            seen.setdefault(number, None)
    return list(seen)


# -------------------------------------------------------------------------- national id
_ID_KEYWORD = (
    r"(?:cmnd|cmt|cmtnd|cccd|can\s*cuoc(?:\s*cong\s*dan)?|chung\s*minh(?:\s*nhan\s*dan|\s*thu)?|"
    r"so\s*dinh\s*danh|ho\s*chieu|passport)"
)
_ID12 = re.compile(r"(?<!\d)0\d{2}[\s.\-]?\d{3}[\s.\-]?\d{3}[\s.\-]?\d{3}(?!\d)")
_ID_AFTER_KEYWORD = re.compile(
    rf"(?<![a-z]){_ID_KEYWORD}[^\d\n]{{0,25}}(?P<num>\d(?:[\s.\-]?\d){{7,13}})(?!\d)"
)
_ID_BEFORE_KEYWORD = re.compile(
    rf"(?<!\d)(?P<num>\d(?:[\s.\-]?\d){{7,13}})(?!\d)[^\d\n]{{0,12}}(?<![a-z]){_ID_KEYWORD}"
)


def _national_id_spans(folded: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = [m.span() for m in _ID12.finditer(folded)]
    for pattern in (_ID_AFTER_KEYWORD, _ID_BEFORE_KEYWORD):
        for m in pattern.finditer(folded):
            if len(re.sub(r"\D", "", m.group("num"))) in (9, 12):
                spans.append(m.span("num"))
    return spans


# ------------------------------------------------------------------------------ e-mail
_EMAIL_AT = re.compile(r"[a-z0-9][a-z0-9._%+\-]*@[a-z0-9\-]+(?:\.[a-z0-9\-]+)+")
_EMAIL_WORDS = re.compile(
    r"(?<![a-z0-9._%+\-])[a-z0-9][a-z0-9._%+\-]+(?:\s*\(at\)\s*|\s*\[at\]\s*|\s+at\s+|\s+a\s*cong\s+)"
    r"[a-z0-9\-]{2,}(?:\s*(?:\.|\(dot\)|\[dot\]|\s+dot\s+|\s+cham\s+)\s*[a-z]{2,6}){1,3}(?![a-z])"
)


def _email_spans(folded: str) -> list[tuple[int, int]]:
    return [m.span() for m in _EMAIL_AT.finditer(folded)] + [m.span() for m in _EMAIL_WORDS.finditer(folded)]


# ------------------------------------------------------------------------------ address
_STREET_WORDS = (
    r"(?:ngo|ngach|hem|duong|pho|ap|thon|xom|khom|khu\s*pho|kdc|kdt|khu\s*do\s*thi|chung\s*cu|"
    r"khu\s*tap\s*the|ktt|tdp|to\s*dan\s*pho)"
)
_HOUSE = r"\d{1,4}[a-z]?(?:\s*[/\-]\s*\d{1,4}[a-z]?){0,3}"
_ADMIN_NAME = r"(?:\d{1,2}|[a-z]+(?:\s[a-z]+)?)"
_ADMIN_TAIL = (
    rf"(?:\s*,?\s*(?:(?:phuong|xa|quan|huyen|thi\s*tran|thanh\s*pho|tp|tinh)\.?\s*{_ADMIN_NAME}"
    rf"|(?:p|q)\.?\s*\d{{1,2}}(?![a-z0-9]))){{0,4}}"
)
_ADDR_HOUSE_STREET = re.compile(
    rf"(?<![a-z0-9])(?:so\s*nha\s*|nha\s*so\s*|so\s*)?{_HOUSE}\s*,?\s*{_STREET_WORDS}\s+(?:[a-z0-9]+\s?){{1,4}}"
    + _ADMIN_TAIL
)
_ADDR_STREET_HOUSE = re.compile(
    r"(?<![a-z])(?:duong|pho|ngo|ngach|hem)\s+(?:[a-z0-9]+\s+){1,4}?so\s*(?:nha\s*)?\d{1,4}[a-z]?(?:/\d{1,4})?"
    + _ADMIN_TAIL
)
_BUILDING_UNIT = r"(?:toa|block|tang|lau|phong|can\s*ho)\s*[a-z]?\d{1,4}[a-z0-9]*(?![a-z])"
_ADDR_BUILDING = re.compile(
    r"(?<![a-z])(?:"
    r"(?:can\s*ho|toa|block)\s*[a-z]?\d{1,4}[a-z0-9]*(?![a-z])"
    r"|chung\s*cu\s+(?:[a-z0-9]+\s?){1,3}"
    r")" + rf"(?:\s*,?\s*{_BUILDING_UNIT})*"
)
_ADDR_KEYWORD = re.compile(
    r"(?<![a-z])dia\s*chi(?:\s*(?:nha|cua\s*(?:em|minh|toi|con|chau)))?\s*(?:la|o|:|-)?\s*[:\-]?\s*"
    r"(?P<rest>[^\n.;!?]{4,90})"
)
_ADDR_REST_IS_QUESTION = re.compile(
    r"^(?:cua\s+)?(?:phong\s*kham|clinic|pema|ben\s*(?:em|minh|ban|phong)|o\s*dau|la\s*gi|the\s*nao|dau\b)"
)
_ADDR_REST_IS_SPECIFIC = re.compile(
    r"(?:\d|duong|pho|ngo|ngach|hem|phuong|quan|xa|huyen|thon|ap(?![a-z])|xom|toa|chung\s*cu)"
)


def _address_spans(folded: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in (_ADDR_HOUSE_STREET, _ADDR_STREET_HOUSE, _ADDR_BUILDING):
        spans.extend(m.span() for m in pattern.finditer(folded))
    for m in _ADDR_KEYWORD.finditer(folded):
        rest = m.group("rest").strip()
        if _ADDR_REST_IS_QUESTION.match(rest):
            continue
        if _ADDR_REST_IS_SPECIFIC.search(rest):
            spans.append(m.span("rest"))
    return spans


# --------------------------------------------------------------------------- birth date
_BIRTH_KEYWORD = r"(?:sinh\s*(?:ngay|nhat|vao)|ngay\s*sinh|ns|nsinh|dob|date\s*of\s*birth|sinh)"
_BIRTH_NUMERIC = re.compile(
    rf"(?<![a-z]){_BIRTH_KEYWORD}\s*(?:la|vao|ngay)?\s*[:\-]?\s*"
    r"(?P<date>\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*(?:\d{4}|\d{2}))(?!\d)"
)
_BIRTH_WORDS = re.compile(r"(?<![a-z])sinh\s*ngay\s*(?P<date>\d{1,2}\s*thang\s*\d{1,2}\s*nam\s*\d{4})(?!\d)")


def _birthdate_spans(folded: str) -> list[tuple[int, int]]:
    return [m.span("date") for p in (_BIRTH_NUMERIC, _BIRTH_WORDS) for m in p.finditer(folded)]


# ------------------------------------------------------------------------------- names
_TITLES = (
    r"(?:anh|chi|em|co|chu|bac|ba|ong|ban|thay|di|cau|mo|bo|me|con|cau|dua|chau|"
    r"mrs|mr|ms|miss)"
)
_INTRO = re.compile(
    r"(?<![a-z])(?:ten\s*(?:cua\s*)?(?:em|minh|toi|con|anh|chi|chau|ban|nguoi\s*benh|benh\s*nhan)?\s*la|"
    r"(?:toi|minh|em|con|chau|anh|chi)\s+la)\s+"
)
_INTRO_STOPWORDS = frozenset(
    {"khach", "benh", "nguoi", "mot", "ban", "nhan", "moi", "ai", "chua", "khong", "rat"}
)  # fmt: skip
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


_MIN_KNOWN_NAME_CHARS = 3
"""A known name shorter than this ("A") would mask every standalone letter of a message."""


@dataclass(frozen=True)
class KnownName:
    """A name the caller already knows (channel ``sender_name``, the verified patient's ``full_name``)."""

    name: str
    patient_code: str | None = None
    """Set for the VERIFIED patient: the name becomes ``[KH_<code>]`` and is restorable."""


def _name_patterns(known: KnownName) -> list[re.Pattern[str]]:
    words = fold_text(to_nfc(known.name)).split()
    if not words or len("".join(words)) < _MIN_KNOWN_NAME_CHARS:
        return []
    patterns: list[re.Pattern[str]] = []
    full = r"\s+".join(re.escape(w) for w in words)
    patterns.append(re.compile(rf"(?<![a-z0-9]){full}(?![a-z0-9])"))
    if len(words) >= 3:
        tail = r"\s+".join(re.escape(w) for w in words[-2:])
        patterns.append(re.compile(rf"(?<![a-z0-9]){tail}(?![a-z0-9])"))
    given = re.escape(words[-1])
    if len(words[-1]) >= 2:
        patterns.append(re.compile(rf"(?<![a-z0-9]){_TITLES}\s+(?P<given>{given})(?![a-z0-9])"))
    return patterns


def _known_name_spans(folded: str, known_names: Iterable[KnownName]) -> list[tuple[int, int, KnownName]]:
    spans: list[tuple[int, int, KnownName]] = []
    for known in known_names:
        for pattern in _name_patterns(known):
            for m in pattern.finditer(folded):
                span = m.span("given") if "given" in pattern.groupindex else m.span()
                spans.append((span[0], span[1], known))
    return spans


def _introduced_name_spans(original: str, folded: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for m in _INTRO.finditer(folded):
        start = m.end()
        end = start
        count = 0
        pos = start
        while count < 4:
            word = _WORD.match(original, pos)
            if word is None:
                break
            text = word.group()
            if not text[0].isupper() or fold_text(text) in _INTRO_STOPWORDS:
                break
            end = word.end()
            count += 1
            gap = re.match(r"[ \t]+", original[end:])
            if gap is None:
                break
            pos = end + gap.end()
        if count:
            spans.append((start, end))
    return spans


# --------------------------------------------------------------------------- the mask
@dataclass(frozen=True)
class PiiSpan:
    start: int
    end: int
    kind: PiiKind
    known: KnownName | None = None


def find_pii_spans(text: str, known_names: Iterable[KnownName] = ()) -> list[PiiSpan]:
    """Non-overlapping PII spans of ``text`` (NFC form), ordered by position."""
    original = to_nfc(text)
    folded = fold_text(original)
    found: list[PiiSpan] = []
    found += [PiiSpan(a, b, PiiKind.EMAIL) for a, b in _email_spans(folded)]
    found += [PiiSpan(a, b, PiiKind.PHONE) for a, b in _phone_spans(folded)]
    found += [PiiSpan(a, b, PiiKind.NATIONAL_ID) for a, b in _national_id_spans(folded)]
    found += [PiiSpan(a, b, PiiKind.BIRTHDATE) for a, b in _birthdate_spans(folded)]
    found += [PiiSpan(a, b, PiiKind.ADDRESS) for a, b in _address_spans(folded)]
    found += [PiiSpan(a, b, PiiKind.NAME, k) for a, b, k in _known_name_spans(folded, known_names)]
    found += [PiiSpan(a, b, PiiKind.NAME) for a, b in _introduced_name_spans(original, folded)]
    found.sort(key=lambda s: (_PRIORITY[s.kind], -(s.end - s.start), s.start))
    accepted: list[PiiSpan] = []
    for span in found:
        if span.end <= span.start:
            continue
        if any(span.start < other.end and other.start < span.end for other in accepted):
            continue
        accepted.append(span)
    accepted.sort(key=lambda s: s.start)
    return accepted


@dataclass(frozen=True)
class MaskResult:
    text: str
    counts: Mapping[PiiKind, int] = field(default_factory=dict[PiiKind, int])
    """How many spans of each kind were masked. Counts only; never the values."""

    @property
    def changed(self) -> bool:
        return bool(self.counts)


_PLACEHOLDER_ANY = re.compile(
    r"\[\s*(?P<label>KH|NGUOI|SDT|CCCD|EMAIL|DIACHI|NGAYSINH)[_\s](?P<id>[A-Za-z0-9]+)\s*\]"
    r"|(?<![A-Za-z0-9])(?P<label2>KH|NGUOI)_(?P<id2>[A-Za-z0-9]+)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def _canonical(kind: PiiKind, value: str) -> str:
    """The form two spellings of the same thing share: "090 123 4567" and "0901234567" are one phone."""
    if kind is PiiKind.PHONE:
        return normalize_vn_phone(value) or re.sub(r"\D", "", value)
    if kind in (PiiKind.NATIONAL_ID, PiiKind.BIRTHDATE):
        return re.sub(r"\D", "", value)
    if kind is PiiKind.EMAIL:
        return re.sub(r"\s+", "", fold_text(value))
    return " ".join(fold_text(value).split())


def _digest(kind: PiiKind, value: str) -> str:
    return hashlib.sha256(f"{kind.value}|{_canonical(kind, value)}".encode()).hexdigest()


class MaskSession:
    """Placeholders of one conversation. Same original, same placeholder; numbering is per kind."""

    def __init__(self) -> None:
        self._by_digest: dict[str, str] = {}
        self._counters: dict[PiiKind, int] = {}
        self._restorable: dict[str, str] = {}
        self._known: list[KnownName] = []

    def add_known_name(self, known: KnownName) -> None:
        if not known.name.strip():
            return
        if any(k.name == known.name and k.patient_code == known.patient_code for k in self._known):
            return
        self._known.append(known)
        if known.patient_code:
            self._restorable[self._patient_placeholder(known.patient_code)] = known.name

    @staticmethod
    def _patient_placeholder(patient_code: str) -> str:
        return f"[{PATIENT_LABEL}_{patient_code}]"

    def _placeholder_for(self, kind: PiiKind, value: str, known: KnownName | None) -> str:
        if known is not None and known.patient_code:
            return self._patient_placeholder(known.patient_code)
        if known is not None:
            value = known.name  # "chị Hoa" and "Nguyễn Thị Hoa" are the same person: one placeholder
        digest = _digest(kind, value)
        existing = self._by_digest.get(digest)
        if existing is not None:
            return existing
        number = self._counters.get(kind, 0) + 1
        self._counters[kind] = number
        placeholder = f"[{LABELS[kind]}_{number}]"
        self._by_digest[digest] = placeholder
        if kind in RESTORABLE_KINDS:
            self._restorable[placeholder] = value
        return placeholder

    def mask(self, text: str) -> MaskResult:
        """Mask one text with this session's known names. Idempotent on already-masked text."""
        original = to_nfc(text)
        spans = find_pii_spans(original, self._known)
        if not spans:
            return MaskResult(text=original)
        out: list[str] = []
        cursor = 0
        counts: dict[PiiKind, int] = {}
        for span in spans:
            out.append(original[cursor : span.start])
            out.append(self._placeholder_for(span.kind, original[span.start : span.end], span.known))
            counts[span.kind] = counts.get(span.kind, 0) + 1
            cursor = span.end
        out.append(original[cursor:])
        return MaskResult(text="".join(out), counts=counts)

    def mask_name(self, name: str) -> str:
        """Placeholder for a bare name (a prompt field), without scanning it as free text."""
        for known in self._known:
            if known.patient_code and fold_text(known.name) == fold_text(to_nfc(name)):
                return self._patient_placeholder(known.patient_code)
        return self._placeholder_for(PiiKind.NAME, to_nfc(name), None)

    def restore(self, text: str) -> str:
        """Put NAMES back (see module docstring); every other placeholder becomes ``[đã ẩn]``."""

        def replace(m: re.Match[str]) -> str:
            label = (m.group("label") or m.group("label2")).upper()
            ident = m.group("id") or m.group("id2")
            key = f"[{label}_{ident}]"
            if label == PATIENT_LABEL:
                key = f"[{PATIENT_LABEL}_{ident}]"
            if label in (PATIENT_LABEL, LABELS[PiiKind.NAME]):
                restored = self._restorable.get(key)
                if restored is None and label == PATIENT_LABEL:
                    restored = next(
                        (v for k, v in self._restorable.items() if k.upper() == key.upper()), None
                    )
                if restored is not None:
                    return restored
            return HIDDEN

        return _PLACEHOLDER_ANY.sub(replace, text)


class MaskVault:
    """Expiring, bounded store of ``MaskSession`` objects, keyed by an opaque token.

    One session lives per (clinic, account, thread): ``session_for`` returns the live one, so a message
    injected in the middle of a turn, the history and the final reply all share placeholders.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 1800.0,
        max_sessions: int = 2000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._clock = clock
        self._sessions: OrderedDict[str, tuple[MaskSession, float]] = OrderedDict()
        self._by_key: dict[str, str] = {}

    def _purge(self) -> None:
        now = self._clock()
        for token in [t for t, (_, seen) in self._sessions.items() if now - seen > self._ttl]:
            self._drop(token)
        while len(self._sessions) > self._max:
            oldest = next(iter(self._sessions))
            self._drop(oldest)

    def _drop(self, token: str) -> None:
        self._sessions.pop(token, None)
        for key in [k for k, t in self._by_key.items() if t == token]:
            del self._by_key[key]

    def session_for(self, key: str) -> tuple[str, MaskSession]:
        self._purge()
        token = self._by_key.get(key)
        if token is not None and token in self._sessions:
            session, _ = self._sessions[token]
            self._sessions[token] = (session, self._clock())
            self._sessions.move_to_end(token)
            return token, session
        token = secrets.token_urlsafe(16)
        session = MaskSession()
        self._sessions[token] = (session, self._clock())
        self._by_key[key] = token
        self._purge()
        return token, session

    def get(self, token: str | None) -> MaskSession | None:
        if token is None:
            return None
        self._purge()
        entry = self._sessions.get(token)
        return entry[0] if entry else None

    def __len__(self) -> int:
        return len(self._sessions)


def mask_pii(text: str, known_names: Iterable[KnownName] = ()) -> MaskResult:
    """One-shot mask with a throwaway session (tests, logs of a user-facing error)."""
    session = MaskSession()
    for known in known_names:
        session.add_known_name(known)
    return session.mask(text)
