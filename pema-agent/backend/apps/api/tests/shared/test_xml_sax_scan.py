# ported from: src/shared/xml-sax-scan.test.ts
"""Pure module (only the SAX parser) - no environment or database."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.knowledge.ooxml_limits import LoiVuotTran
from pema.shared.xml_sax_scan import SaxTag, XmlSaxHandlers, quet_xml_theo_luong

WORDML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def tu_chuoi(*chunks: str) -> Iterator[str]:
    yield from chunks


class _GomChu(XmlSaxHandlers):
    def __init__(self) -> None:
        self.chu = ""
        self.cdata_chu = ""

    def chu_van_ban(self, text: str) -> None:
        self.chu += text

    def cdata(self, text: str) -> None:
        self.cdata_chu += text


def test_gop_chunk_khop_namespace_merges_correctly_when_one_node_is_cut_in_half_by_a_chunk() -> None:
    """gộp đúng khi 1 node bị chunk cắt làm đôi giữa chừng"""
    # This is exactly why chu_van_ban MAY be called several times for one node - simulates a chunk
    # boundary from zip_stream_entry cutting right in the middle of a word.
    h = _GomChu()
    quet_xml_theo_luong(tu_chuoi(f'<w:t xmlns:w="{WORDML_NS}">Xin ch', "ào tất cả</w:t>"), h)
    assert h.chu == "Xin chào tất cả"


def test_gop_chunk_khop_namespace_matches_tags_by_namespace_uri_not_by_prefix_or_default_namespace() -> None:
    """khớp thẻ theo NAMESPACE URI, không phụ thuộc prefix hay namespace mặc định"""

    class H(XmlSaxHandlers):
        def __init__(self) -> None:
            self.uris: list[str] = []

        def mo_the(self, tag: SaxTag) -> None:
            self.uris.append(tag.uri)

    h = H()
    for xml in (
        f'<w:t xmlns:w="{WORDML_NS}">a</w:t>',  # prefix w:
        f'<la:t xmlns:la="{WORDML_NS}">a</la:t>',  # odd prefix
        f'<t xmlns="{WORDML_NS}">a</t>',  # default namespace, no prefix
    ):
        quet_xml_theo_luong(tu_chuoi(xml), h)
    assert h.uris == [WORDML_NS, WORDML_NS, WORDML_NS]


def test_gop_chunk_khop_namespace_cdata_goes_through_its_own_event_not_mixed_into_chu_van_ban() -> None:
    """CDATA phát qua sự kiện cdata riêng, không lẫn vào chuVanBan"""
    h = _GomChu()
    quet_xml_theo_luong(tu_chuoi("<r>chu<![CDATA[<tho>]]></r>"), h)
    assert h.chu == "chu"
    assert h.cdata_chu == "<tho>"


def test_gop_chunk_khop_namespace_self_closing_tag_fires_both_mo_the_and_dong_the_back_to_back() -> None:
    """thẻ tự đóng phát cả moThe LẪN dongThe, liền nhau"""

    class H(XmlSaxHandlers):
        def __init__(self) -> None:
            self.goi: list[str] = []

        def mo_the(self, tag: SaxTag) -> None:
            self.goi.append(f"mo:{tag.local}")

        def dong_the(self, tag: SaxTag) -> None:
            self.goi.append(f"dong:{tag.local}({str(tag.is_self_closing).lower()})")

    h = H()
    quet_xml_theo_luong(tu_chuoi("<a><b/></a>"), h)
    assert h.goi == ["mo:a", "mo:b", "dong:b(true)", "dong:a(false)"]


def test_self_closing_detection_covers_attributes_with_gt_and_chunk_boundaries() -> None:
    """(thêm, do đổi parser) nhận diện thẻ tự đóng đúng khi thuộc tính chứa '>' và khi thẻ bị cắt giữa hai chunk"""

    class H(XmlSaxHandlers):
        def __init__(self) -> None:
            self.ket_qua: list[tuple[str, bool]] = []

        def mo_the(self, tag: SaxTag) -> None:
            self.ket_qua.append((tag.local, tag.is_self_closing))

    h = H()
    quet_xml_theo_luong(tu_chuoi('<r><c a="x/>y"/><d b=', '"1"/><e>a/></e><f></f></r>'), h)
    assert h.ket_qua == [("r", False), ("c", True), ("d", True), ("e", False), ("f", False)]


def test_tran_do_sau_va_dich_loi_depth_over_the_256_ceiling_is_refused_with_the_too_deep_sentence() -> None:
    """độ sâu vượt trần 256 bị từ chối, ném đúng câu 'lồng quá sâu'"""
    xml = "<r>" * 300
    with pytest.raises(LoiVuotTran, match="lồng quá sâu"):
        quet_xml_theo_luong(tu_chuoi(xml), XmlSaxHandlers())


def test_tran_do_sau_va_dich_loi_malformed_xml_is_translated_to_the_invalid_xml_sentence() -> None:
    """XML sai cú pháp (thẻ đóng không khớp) bị dịch sang câu 'XML không hợp lệ'"""
    with pytest.raises(ValueError, match="XML không hợp lệ"):
        quet_xml_theo_luong(tu_chuoi("<a><b></a></b>"), XmlSaxHandlers())


def test_tran_do_sau_va_dich_loi_a_doctype_is_refused() -> None:
    """(thêm, do đổi parser) DOCTYPE/entity bị từ chối - cửa của bom mở rộng entity"""
    bom = '<?xml version="1.0"?><!DOCTYPE lol [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><r>&b;</r>'
    with pytest.raises(ValueError, match="XML không hợp lệ"):
        quet_xml_theo_luong(tu_chuoi(bom), XmlSaxHandlers())


def test_tran_do_sau_va_dich_loi_error_raised_by_the_chunk_source_itself_is_not_wrapped() -> None:
    """lỗi ném từ chính nguồn chunk (ví dụ trần zip-stream-entry.ts) KHÔNG bị bọc lại"""

    # Proves the layer boundary: quet_xml_theo_luong translates only errors raised INSIDE Parse (the parser
    # or the depth counter) - an error from ``chunks`` itself (standing for ``zip_stream_entry`` exceeding a
    # ceiling) must propagate untouched, NOT become "XML không hợp lệ: ..." (which would lose the "vượt quá
    # giới hạn" meaning the caller relies on to tell the errors apart).
    def nguon_hong() -> Iterator[str]:
        yield "<a>"
        raise RuntimeError("Entry ABC giải nén ra vượt quá giới hạn 32 MB - nghi ngờ zip bomb")

    with pytest.raises(RuntimeError) as excinfo:
        quet_xml_theo_luong(nguon_hong(), XmlSaxHandlers())
    assert str(excinfo.value) == "Entry ABC giải nén ra vượt quá giới hạn 32 MB - nghi ngờ zip bomb", (
        "lỗi phải truyền NGUYÊN VĂN, không bị bọc thêm tiền tố nào"
    )
