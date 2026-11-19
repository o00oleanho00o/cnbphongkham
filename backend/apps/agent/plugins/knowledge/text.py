"""Reading a document: its YAML head, its headings, the chunks it is cut into, the words a search matches
on and what deserves a warning before it is added. Pure functions, no database.

Chunks follow the document's own structure: one per ``##``/``###`` section (with the headings above it as its
path), a section too short is joined to the one before, a section too long is cut at paragraphs. Words are
folded (no Vietnamese marks, ``đ`` -> ``d``, lower case) and two neighbouring syllables also count as one
word, so "trị nám" matches better than "trị" and "nám" apart.
"""

from __future__ import annotations

import hashlib
import itertools
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal

Lifecycle = Literal["active", "draft", "superseded", "expired", "adversarial"]
Audience = Literal["patient", "staff"]

MIN_CHUNK_CHARS: Final = 60
"""A section shorter than this (a heading with a line under it) joins the chunk before it."""
MAX_CHUNK_CHARS: Final = 1500
MAX_QUERY_TERMS: Final = 40
LIFECYCLES: Final[frozenset[str]] = frozenset({"active", "draft", "superseded", "adversarial"})

_STOPWORDS_TEXT: Final = """
a ah anh ba bao ban bi bo cac cai can cho chi chua co con cua cung da dang day de den deu di do duoc em gi gio
hay hoac hoi khi khong la lai lam len luc ma minh mot muon nao nay neu nhe nhieu nhu nhung no o oi ong roi sao
se tai the thi thoi toi tren trong tu va vay ve vi voi xin
"""
STOPWORDS: Final[frozenset[str]] = frozenset(_STOPWORDS_TEXT.split())

QUERY_SYNONYMS: Final[dict[str, tuple[str, ...]]] = {
    "bao nhieu tien": ("gia",),
    "het bao nhieu": ("gia",),
    "chi phi": ("gia",),
    "khieu nai": ("phan anh",),
    "phan nan": ("phan anh",),
    "o dau": ("dia chi", "chi nhanh"),
    "may gio": ("gio mo cua",),
    "kem": ("san pham",),
    "giam gia": ("khuyen mai", "uu dai"),
    "coc": ("dat coc",),
    "doi lich": ("doi lich", "huy lich"),
    "lau khong": ("thoi gian",),
}
"""Phrases a customer uses (folded) and the words clinic documents use for the same thing."""
SPOKEN_ONLY: Final[dict[str, str]] = {"bao nhieu tien": "bao nhieu", "het bao nhieu tien": "bao nhieu"}
"""Spoken phrases whose words would mislead a keyword search ("tiền" is rare and pulls in refunds): the
question is searched without them (their meaning comes back through ``QUERY_SYNONYMS``)."""
HEADING: Final = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
PHONE: Final = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.-]?\d){8,10}(?!\d)")
CITIZEN_ID: Final = re.compile(r"(?<!\d)\d{12}(?!\d)")
EMAIL: Final = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def fold(text: str) -> str:
    """Lower case, without Vietnamese marks: "Điều trị NÁM" -> "dieu tri nam"."""
    lowered = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def terms(text: str, *, drop_stopwords: bool = False) -> list[str]:
    """The words a search matches on: the folded words and each pair of neighbours joined ("trinam")."""
    found = words(text)
    if not drop_stopwords:
        return found + [a + b for a, b in itertools.pairwise(found)]
    kept = [w for w in found if w not in STOPWORDS]
    return kept + [a + b for a, b in itertools.pairwise(found) if not (a in STOPWORDS and b in STOPWORDS)]


def query_terms(question: str) -> list[str]:
    """The distinct terms of a question, without the words every question has, plus the words documents use
    for what a customer says another way (``QUERY_SYNONYMS``), at most ``MAX_QUERY_TERMS``."""
    folded = f" {' '.join(words(question))} "
    extra = [word for phrase, said in QUERY_SYNONYMS.items() if f" {phrase} " in folded for word in said]
    plain = folded
    for phrase, kept in SPOKEN_ONLY.items():
        plain = plain.replace(f" {phrase} ", f" {kept} ")
    found = [*terms(plain, drop_stopwords=True), *terms(" ".join(extra))]
    return list(dict.fromkeys(found))[:MAX_QUERY_TERMS]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def embed_text_of(title: str, path: str, body: str) -> str:
    """What a chunk is embedded as: its document's title, its headings and its text."""
    return f"{title}\n{path}\n\n{body}"


def text_hash(text: str) -> str:
    """The key of a vector. Unlike ``content_hash`` it does not strip: the migration's SQL does not either."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- the YAML head -----------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Head:
    doc_code: str | None = None
    title: str | None = None
    tenant_id: str | None = None
    version: str | None = None
    lifecycle: Lifecycle | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    audience: Audience | None = None
    ingest_role: Literal["kb", "challenge"] | None = None


def split_head(text: str) -> tuple[Head, str]:
    """The YAML head (a ``---`` block of ``key: value`` lines at the very top) and the body after it."""
    normalised = text.replace("\r\n", "\n").lstrip("﻿")
    match = re.match(r"^---\n(.*?)\n---\n?", normalised, re.DOTALL)
    if match is None:
        return Head(), normalised
    values = dict(_pairs(match.group(1)))
    return _head(values), normalised[match.end() :]


def _pairs(block: str) -> list[tuple[str, str]]:
    lines = [line.partition(":") for line in block.splitlines()]
    return [(key.strip(), _unquote(value.strip())) for key, sep, value in lines if sep and key.strip()]


def _unquote(value: str) -> str:
    """Quoted text as is; a bare value without its trailing `` # comment`` (as the browser half reads it)."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return re.sub(r"\s+#.*$", "", value).strip()


def _head(values: dict[str, str]) -> Head:
    status = values.get("status", "")
    audience = values.get("audience", "")
    role = values.get("ingest_role", "")
    return Head(
        doc_code=_text(values.get("doc_id")),
        title=_text(values.get("title")),
        tenant_id=_text(values.get("tenant_id")),
        version=_text(values.get("version")),
        lifecycle=status if status in LIFECYCLES else None,  # type: ignore[arg-type]  # checked against LIFECYCLES
        effective_from=_date(values.get("effective_from")),
        effective_to=_date(values.get("effective_to")),
        audience="patient" if audience == "patient" else "staff" if audience == "staff" else None,
        ingest_role="challenge" if role == "challenge" else "kb" if role == "kb" else None,
    )


def _text(value: str | None) -> str | None:
    if value is None or value.lower() in ("", "null", "none", "~"):
        return None
    return value


def _date(value: str | None) -> date | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


# -- headings and chunks -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OutlineNode:
    level: int
    title: str
    chunks: int
    chars: int


@dataclass(frozen=True, slots=True)
class Piece:
    """One chunk before it is stored: the headings above it and its text."""

    path: str
    text: str


@dataclass(slots=True)
class _Section:
    level: int
    title: str
    path: tuple[str, ...]
    lines: list[str] = field(default_factory=list[str])

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


def sections(body: str) -> list[_Section]:
    """The body cut at every heading; text before the first heading is a section of its own."""
    found: list[_Section] = [_Section(0, "", ())]
    stack: list[tuple[int, str]] = []
    for line in body.split("\n"):
        heading = HEADING.match(line)
        if heading is None:
            found[-1].lines.append(line)
            continue
        level, title = len(heading.group(1)), heading.group(2).strip()
        stack = [*(item for item in stack if item[0] < level), (level, title)]
        found.append(_Section(level, title, tuple(t for _, t in stack)))
    return found


def outline(body: str) -> list[OutlineNode]:
    cut = sections(body)
    counts = _chunk_counts(cut)
    return [
        OutlineNode(section.level, section.title, counts.get(index, 0), len(section.text))
        for index, section in enumerate(cut)
        if section.level > 0
    ]


def chunk(body: str, title: str) -> list[Piece]:
    """The chunks of a document, in order (see the module's note)."""
    return [piece for _, piece in _pieces(sections(body), title)]


def _chunk_counts(cut: list[_Section]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for index, _ in _pieces(cut, ""):
        counts[index] = counts.get(index, 0) + 1
    return counts


def _pieces(cut: list[_Section], title: str) -> list[tuple[int, Piece]]:
    merged: list[tuple[int, str, str]] = []
    for index, section in enumerate(cut):
        text = section.text
        if not text:
            continue
        path = " > ".join(section.path) or title
        if merged and len(text) < MIN_CHUNK_CHARS:
            last_index, last_path, last_text = merged[-1]
            heading = section.path[-1] if section.path else ""
            merged[-1] = (last_index, last_path, f"{last_text}\n\n{heading}\n{text}".strip())
            continue
        merged.append((index, path, text))
    return [(index, Piece(path, part)) for index, path, text in merged for part in _split_long(text)]


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    parts: list[str] = [""]
    for paragraph in re.split(r"\n\s*\n", text):
        if parts[-1] and len(parts[-1]) + len(paragraph) + 2 > MAX_CHUNK_CHARS:
            parts.append("")
        parts[-1] = f"{parts[-1]}\n\n{paragraph}".strip()
    return [
        part[i : i + MAX_CHUNK_CHARS] for part in parts if part for i in range(0, len(part), MAX_CHUNK_CHARS)
    ]


def count_tables(body: str) -> int:
    """Markdown tables (a header row followed by a ``|---|`` line)."""
    return len(re.findall(r"^\s*\|.*\|\s*\n\s*\|[\s:|-]+\|\s*$", body, re.MULTILINE))


# -- warnings ----------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Warning:
    code: str
    level: Literal["info", "warn", "error"]
    text: str
    fix: str | None = None


def content_warnings(body: str, nodes: list[OutlineNode]) -> list[Warning]:
    found: list[Warning] = []
    if body.strip() and not nodes:
        found.append(
            Warning(
                "no_headings",
                "warn",
                "Không thấy tiêu đề nào: cả tài liệu sẽ được chia theo đoạn văn, tìm sẽ kém chính xác hơn.",
                "Thêm tiêu đề ## cho từng mục rồi nạp lại.",
            )
        )
    personal = [
        name
        for name, rule in (("số điện thoại", PHONE), ("số CCCD", CITIZEN_ID), ("email", EMAIL))
        if rule.search(body)
    ]
    if personal:
        found.append(
            Warning(
                "personal_data",
                "info",
                f"Có {', '.join(personal)} trong văn bản. Kho không dành cho dữ liệu bệnh nhân.",
                "Nếu là thông tin của phòng khám thì giữ; nếu của khách thì xóa khỏi tệp.",
            )
        )
    return found
