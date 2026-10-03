"""Pure text helpers of the staff guide: article summary, passages and the ranking behind "Hoi Pema".

New module. No database, no clock. The ranking is the Okapi BM25 the knowledge base already uses for its
keyword side (``pema.knowledge.kb_fts_query``), applied to the passages of the guide articles instead of kb
chunks; the words are folded the same way (``bo_dau_tieng_viet``), so "dời lịch" finds "doi lich". It is a
search over clinic-written procedure text: no model is called and nothing is generated, so it cannot invent an
answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pema.knowledge.kb_fts_query import diem_bm25, idf_bm25, tach_tu_khoa

SUMMARY_MAX: Final = 240
PASSAGE_MAX: Final = 700
MAX_QUESTION_WORDS: Final = 24

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_MARKUP = re.compile(r"[*_`>]+|\[([^\]]*)\]\([^)]*\)")
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

# Question words that carry no topic in Vietnamese ("làm sao để dời lịch": only "doi" and "lich" matter).
_STOP_WORDS: Final = frozenset(
    [
        "la",
        "va",
        "cua",
        "the",
        "nao",
        "gi",
        "khi",
        "nhu",
        "co",
        "khong",
        "de",
        "cho",
        "toi",
        "minh",
        "lam",
        "sao",
        "ra",
        "bi",
        "o",
        "trong",
        "mot",
        "cac",
        "nhung",
        "duoc",
        "se",
        "da",
        "thi",
        "ma",
        "hay",
        "hoac",
        "voi",
        "tu",
        "den",
        "xin",
        "vui",
        "long",
    ]
)


@dataclass(frozen=True, slots=True)
class Passage:
    heading: str
    text: str


def _plain(line: str) -> str:
    return _MARKUP.sub(lambda m: m.group(1) or "", line).strip()


def summary_of(body: str) -> str:
    """First paragraph that is not a heading, as plain text, cut to ``SUMMARY_MAX``."""
    paragraph: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            if paragraph:
                break
            continue
        if _HEADING.match(line):
            if paragraph:
                break
            continue
        paragraph.append(_plain(_LIST_MARK.sub("", line)))
    text = " ".join(p for p in paragraph if p)
    if len(text) <= SUMMARY_MAX:
        return text
    return text[: SUMMARY_MAX - 1].rstrip() + "…"


def split_passages(body: str) -> list[Passage]:
    """One passage per section (the lead before the first heading has an empty heading). A section longer
    than ``PASSAGE_MAX`` is cut at paragraph or line breaks so a hit stays readable."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for raw in body.splitlines():
        match = _HEADING.match(raw)
        if match:
            sections.append((_plain(match.group(1)), []))
        else:
            sections[-1][1].append(raw.rstrip())
    passages: list[Passage] = []
    for heading, lines in sections:
        block = "\n".join(lines).strip()
        if not block:
            continue
        current = ""
        for piece in re.split(r"\n\s*\n|\n(?=\s*(?:[-*+]|\d+[.)])\s)", block):
            piece = piece.strip()
            if not piece:
                continue
            if current and len(current) + len(piece) + 1 > PASSAGE_MAX:
                passages.append(Passage(heading, current))
                current = ""
            current = f"{current}\n{piece}" if current else piece
        if current:
            passages.append(Passage(heading, current[:PASSAGE_MAX]))
    return passages


def question_words(question: str) -> list[str]:
    words = [w.lower() for w in tach_tu_khoa(question)]
    useful = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
    return list(dict.fromkeys(useful or words))[:MAX_QUESTION_WORDS]


@dataclass(frozen=True, slots=True)
class Scored:
    index: int
    score: float


def rank(words: list[str], documents: list[str], *, titles: list[str] | None = None) -> list[Scored]:
    """BM25 over ``documents`` (already plain text); a word that also appears in the matching ``titles[i]``
    adds half its weight again, because a heading that names the topic is the best evidence there is.
    Documents that match no word are dropped; the rest come best first, ties by position."""
    if not words or not documents:
        return []
    folded = [[t.lower() for t in tach_tu_khoa(d)] for d in documents]
    n = len(folded)
    average = sum(len(f) for f in folded) / n
    idf: dict[str, float] = {}
    for word in words:
        containing = sum(1 for tokens in folded if word in tokens)
        idf[word] = idf_bm25(n, containing)
    title_tokens: list[set[str]] = [
        {t.lower() for t in tach_tu_khoa(x)} for x in (titles if titles else [""] * len(documents))
    ]
    scored: list[Scored] = []
    for index, tokens in enumerate(folded):
        score = diem_bm25(words, tokens, idf, average)
        if score <= 0:
            continue
        score += sum(0.5 * idf[w] for w in words if w in title_tokens[index])
        scored.append(Scored(index, score))
    scored.sort(key=lambda s: (-s.score, s.index))
    return scored
