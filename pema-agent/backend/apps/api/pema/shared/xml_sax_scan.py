# ported from: src/shared/xml-sax-scan.ts
"""Wrapper over a namespace-aware SAX parser for the docx/xlsx reading path: feeds a stream of text chunks,
counts the tag nesting depth and raises a Vietnamese error when a ceiling is crossed or the XML is
malformed.

Does NOT register an error handler that recovers: the parser's failure RAISES straight out (instead of
quietly recovering and reading on with corrupted data). XML from a stranger that is malformed must be
blocked hard.

Do not write a linear scanner by hand: the original research measured that a home-made ``indexOf`` scanner
was wrong in 5 of 5 edge cases (attribute values containing ``>``, comments, CDATA, entities, unknown
namespace prefixes).

Forced deviation (saxes -> ``xml.parsers.expat``, async -> sync):
* ``saxes`` in ``xmlns: true`` mode is ``expat`` with a namespace separator. ``expat`` is the C parser of
  the standard library, the same family ``defusedxml`` wraps; a ``DOCTYPE`` is REFUSED outright (OOXML
  never has one, and a DOCTYPE is the door to entity-expansion bombs and external entities), which is
  stricter than ``saxes`` and costs nothing legitimate;
* ``saxes`` tells ``isSelfClosing`` when a tag opens; ``expat`` cannot, so the start tag is looked up in the
  bytes just fed (``_start_tag_is_self_closing``) when the element opens. The look-up window is the tail of
  the previous chunk plus the current one; a start tag longer than ``_TAIL_BYTES`` (4 KB, abnormal in OOXML)
  reads as not self-closing, the harmless side;
* the chunks come from a plain generator (see ``zip_stream_entry``), so ``quet_xml_theo_luong`` is a plain
  function.
"""

from __future__ import annotations

import re
import xml.parsers.expat as expat
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

from pema.knowledge.ooxml_limits import TRAN_DO_SAU_XML, LoiVuotTran

_TAIL_BYTES: Final = 4096
_START_TAG: Final = re.compile(rb"""<[^>"']*(?:"[^"]*"[^>"']*|'[^']*'[^>"']*)*>""")


@dataclass(frozen=True, slots=True)
class XmlAttr:
    """One attribute with its namespace (``saxes`` ``SaxesAttributeNS``)."""

    local: str
    value: str
    uri: str = ""


@dataclass(slots=True)
class SaxTag:
    """``SaxesTagNS``: only the fields the builders use."""

    uri: str
    local: str
    attributes: dict[str, XmlAttr] = field(default_factory=lambda: {})
    is_self_closing: bool = False


class XmlSaxHandlers:
    """The four callbacks. Every method defaults to doing nothing, so a builder overrides only what it
    reads (the TypeScript type had four optional members).

    ``mo_the``: called when a tag OPENS, a self-closing one included (``<w:p/>`` fires open and close
    back to back). ``dong_the``: called when a tag CLOSES.

    ``chu_van_ban``: called with each piece of text inside the current tag. MAY be called SEVERAL TIMES for
    the same node if a chunk boundary (from ``zip_stream_entry``) cuts that node: the caller must gather
    until the matching ``dong_the`` and never treat one call as the whole content. ``cdata``: CDATA has
    its own event, it does not go through ``chu_van_ban``."""

    def mo_the(self, tag: SaxTag) -> None:
        return None

    def dong_the(self, tag: SaxTag) -> None:
        return None

    def chu_van_ban(self, text: str) -> None:
        return None

    def cdata(self, text: str) -> None:
        return None


def _dich_loi_sax(err: BaseException) -> BaseException:
    """``LoiVuotTran`` is ALREADY the final Vietnamese sentence (the depth counter below, or the caller
    raising from the handlers - for example ``TRAN_TONG_KY_TU_TRICH`` of the docx/xlsx state machine) - not
    translated again. Recognised by ERROR TYPE, not by string matching (fragile, would catch one ceiling
    only)."""
    if isinstance(err, LoiVuotTran):
        return err
    return ValueError(f"XML không hợp lệ: {err}")


def _split_name(name: str) -> tuple[str, str]:
    uri, _, local = name.rpartition(" ")
    return uri, local


def quet_xml_theo_luong(chunks: Iterable[str], handlers: XmlSaxHandlers) -> None:
    """Feed the stream of chunks (from ``zip_stream_entry``) into a NEW parser and replay through
    ``handlers``. An error raised by ``chunks`` itself (for example a zip ceiling) does NOT go through
    ``_dich_loi_sax``: only what happens INSIDE ``Parse`` is caught here. Three things can raise from inside
    it: the parser itself (bad syntax), the depth counter below, or ``handlers`` raising UP (for example the
    docx/xlsx state machine finding ``TRAN_TONG_KY_TU_TRICH`` / ``TRAN_SO_COT_EXCEL`` exceeded) - these
    handlers are called synchronously from inside parser events. ``_dich_loi_sax`` translates only the
    first kind."""
    parser = expat.ParserCreate(encoding="utf-8", namespace_separator=" ")
    parser.buffer_text = True
    parser.buffer_size = 64 * 1024
    parser.ordered_attributes = False
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    depth = 0
    in_cdata = False
    window = b""
    window_base = 0
    fed_total = 0
    open_tags: list[SaxTag] = []

    def start_is_self_closing() -> bool:
        pos = parser.CurrentByteIndex - window_base
        if pos < 0:
            return False  # the start tag begins before the window (abnormally long): harmless side
        match = _START_TAG.match(window, pos)
        return match is not None and match.group().endswith(b"/>")

    def on_doctype(*_args: object) -> None:
        raise ValueError("không cho phép khai báo DOCTYPE/entity trong tài liệu")

    def on_start(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth
        depth += 1
        if depth > TRAN_DO_SAU_XML:
            raise LoiVuotTran(f"XML lồng quá sâu (vượt {TRAN_DO_SAU_XML} cấp) - nghi ngờ bom giải nén")
        uri, local = _split_name(name)
        attributes: dict[str, XmlAttr] = {}
        for key, value in attrs.items():
            attr_uri, attr_local = _split_name(key)
            attributes[key] = XmlAttr(local=attr_local, value=value, uri=attr_uri)
        tag = SaxTag(uri=uri, local=local, attributes=attributes, is_self_closing=start_is_self_closing())
        open_tags.append(tag)
        handlers.mo_the(tag)

    def on_end(_name: str) -> None:
        nonlocal depth
        depth -= 1
        handlers.dong_the(open_tags.pop())

    def on_text(text: str) -> None:
        if in_cdata:
            handlers.cdata(text)
        else:
            handlers.chu_van_ban(text)

    def on_cdata_start() -> None:
        nonlocal in_cdata
        in_cdata = True

    def on_cdata_end() -> None:
        nonlocal in_cdata
        in_cdata = False

    parser.StartDoctypeDeclHandler = on_doctype
    parser.EntityDeclHandler = on_doctype
    parser.StartElementHandler = on_start
    parser.EndElementHandler = on_end
    parser.CharacterDataHandler = on_text
    parser.StartCdataSectionHandler = on_cdata_start
    parser.EndCdataSectionHandler = on_cdata_end

    for chunk in chunks:
        data = chunk.encode("utf-8")
        tail = window[-_TAIL_BYTES:]
        window = tail + data
        window_base = fed_total - len(tail)
        fed_total += len(data)
        try:
            parser.Parse(data, False)
        except (expat.ExpatError, ValueError, LoiVuotTran) as err:
            raise _dich_loi_sax(err) from err
    try:
        parser.Parse(b"", True)
    except (expat.ExpatError, ValueError, LoiVuotTran) as err:
        raise _dich_loi_sax(err) from err
