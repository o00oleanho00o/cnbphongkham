"""Vietnamese text normalisation shared by the red-flag detector and the PII mask.

New module (not a port: zalo-agent has ``shared/bo-dau-tieng-viet.ts``, owned by package D3 and not
available to this package; the policy needs two extra properties the original does not).

Patients write on a phone: with diacritics, without, with the wrong tone, with abbreviations and with
stretched letters ("chayyy mau"). Safety matching therefore runs on a FOLDED copy of the text. Two
variants exist because the two callers need different guarantees:

* ``fold_text``: lower case, no diacritics, ``đ`` -> ``d``, and EXACTLY one output character per input
  character (after NFC). Offsets found in the folded text are valid offsets in the original, which is
  what the PII mask needs to cut a span out of the real message.
* ``normalize_for_flags``: the same fold, then cosmetic clean-up (separators inside a word, stretched
  letters, a zero typed instead of ``o``) that shortens the text. It keeps ``source_index``, the index
  in the original text of every folded character, so the red-flag rules can still look at the
  diacritics the patient typed to tell "sốt" (fever) from "sót" (left over).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

_SEPARATORS_INSIDE_WORD = frozenset(".-_*·'’`​‌‍­")


def fold_char(ch: str) -> str:
    """One character in, one character out: lower case without diacritics."""
    lowered = ch.lower()
    if len(lowered) != 1:
        return ch
    if lowered == "đ":
        return "d"
    decomposed = unicodedata.normalize("NFD", lowered)
    if len(decomposed) > 1 and unicodedata.combining(decomposed[1]):
        return decomposed[0]
    return lowered


def fold_text(text: str) -> str:
    """Length-preserving fold of an NFC string (call ``to_nfc`` first when the input may be decomposed)."""
    return "".join(fold_char(ch) for ch in text)


def to_nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


@dataclass(frozen=True)
class NormalizedText:
    """Folded text for matching plus the way back to the original characters."""

    original: str
    """NFC form of the input; ``source_index`` points into it."""
    folded: str
    source_index: tuple[int, ...]
    """``source_index[i]`` = index in ``original`` of ``folded[i]``."""

    def original_span(self, start: int, end: int) -> str:
        """The original characters covered by ``folded[start:end]`` (as typed, with their tone marks)."""
        if start >= end or not self.source_index:
            return ""
        first = self.source_index[start]
        last = self.source_index[end - 1]
        return self.original[first : last + 1]


def normalize_for_flags(text: str) -> NormalizedText:
    """Fold and clean ``text`` for the red-flag rules (see module docstring).

    Beyond the fold: compatibility forms are read as their plain letters (NFKC per character, so a full-width
    ``ｃｈａｙ`` or a styled letter matches), every invisible format character (zero width space/joiner, soft
    hyphen, bidi mark: category ``Cf``) is dropped wherever it sits, and every exotic space becomes a plain
    one. Each emitted character keeps the index of the ORIGINAL character it came from."""
    original = to_nfc(text)
    chars: list[str] = []
    index: list[int] = []
    run_char = ""
    for i, raw in enumerate(original):
        if unicodedata.category(raw) == "Cf":
            continue
        compat = unicodedata.normalize("NFKC", raw)
        pieces = [" "] if raw.isspace() else [fold_char(c) for c in (compat or raw)]
        for folded in pieces:
            # a separator glued between two letters ("m.ủ", "s-ốt") is dropped
            if (
                folded in _SEPARATORS_INSIDE_WORD
                and chars
                and chars[-1].isalpha()
                and i + 1 < len(original)
                and fold_char(original[i + 1]).isalpha()
            ):
                continue
            # a zero typed between letters is an "o" ("s0t", "kh0 th0")
            if (
                folded == "0"
                and chars
                and chars[-1].isalpha()
                and i + 1 < len(original)
                and fold_char(original[i + 1]).isalpha()
            ):
                folded = "o"
            # stretched letters ("chayyy", "sốtt", "khoooo"): a run of one letter collapses to one letter.
            # Vietnamese has no native double letter after the fold, so no real word is damaged.
            if folded.isalpha() and folded == run_char:
                continue
            run_char = folded if folded.isalpha() else ""
            chars.append(folded)
            index.append(i)
    return NormalizedText(original=original, folded="".join(chars), source_index=tuple(index))
