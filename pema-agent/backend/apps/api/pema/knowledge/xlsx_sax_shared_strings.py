# ported from: src/knowledge/xlsx-sax-shared-strings.ts
"""``xl/sharedStrings.xml`` -> list of strings in EXACTLY the index order that cells of kind ``t="s"``
refer to. Replaces the old ``SI_RE``/``T_TAG_RE``."""

from __future__ import annotations

from typing import Final

from pema.shared.xml_sax_scan import SaxTag, XmlSaxHandlers

SPREADSHEETML_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def thay_the_escape_excel(s: str) -> str:
    """Excel escapes control characters in a string in its own way (for example a line break inside a
    cell): the convention lives INSIDE the text data, the XML parser does not touch it (this is not an XML
    entity), so the reader must replace it itself."""
    return s.replace("_x000D_", "\n")


class SharedStringsSaxBuilder(XmlSaxHandlers):
    def __init__(self) -> None:
        self._chuoi_dung_chung: list[str] = []
        self._do_sau_rph = 0  # >0: inside <rPh> (furigana phonetics) - NOT counted as text
        self._dang_trong_t = False
        self._bo_dem = ""

    def lay_chuoi_dung_chung(self) -> list[str]:
        return self._chuoi_dung_chung

    def mo_the(self, tag: SaxTag) -> None:
        if tag.uri != SPREADSHEETML_NS:
            return
        if tag.local == "si":
            self._bo_dem = ""
        elif tag.local == "rPh":
            self._do_sau_rph += 1
        elif tag.local == "t" and self._do_sau_rph == 0:
            self._dang_trong_t = True

    def dong_the(self, tag: SaxTag) -> None:
        if tag.uri != SPREADSHEETML_NS:
            return
        if tag.local == "si":
            self._chuoi_dung_chung.append(thay_the_escape_excel(self._bo_dem))
        elif tag.local == "rPh":
            self._do_sau_rph -= 1
        elif tag.local == "t":
            self._dang_trong_t = False

    def chu_van_ban(self, text: str) -> None:
        # A rich-text string (the **bold** marker of ``render-xlsx``) is split into several <r><t> nested in
        # 1 <si> - gathering every <t> that is not in rPh gives the right text, nested <r> or not.
        if self._dang_trong_t:
            self._bo_dem += text


def tao_shared_strings_sax_builder() -> SharedStringsSaxBuilder:
    return SharedStringsSaxBuilder()
