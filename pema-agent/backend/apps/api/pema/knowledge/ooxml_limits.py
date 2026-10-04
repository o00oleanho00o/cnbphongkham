# ported from: src/knowledge/ooxml-limits.ts
"""Every ceiling of the docx/xlsx reading path (knowledge base) in ONE place, so that changing a ceiling
means editing this file only.

Basis of each number (original research note, section 5.6): a 768 MB container for a self-hosted bot ->
Node old space 384 MB shared by every Zalo account, so one OOXML turn should peak around 200 MB. Largest
REAL Word/Excel files measured: a single entry of 7.13 MB, 20.6 MB decompressed in total; every ceiling
below is a few times above that.

Forced deviation: none in the values. The memory figures describe the Node budget the numbers were
derived from; in the Python port the worker process has its own memory ceiling
(``chay_trich_xuat_tach_luong.TRAN_RAM_WORKER_MB``) and these limits keep their role: they bound what a
hostile archive can make the parser do BEFORE the process ceiling is reached.
"""

from __future__ import annotations

from typing import Final, Literal

TRAN_TONG_GIAI_NEN: Final = 64 * 1024 * 1024
"""Ceiling on the TOTAL decompressed data of the WHOLE archive (summed over every entry read in one
session): the ONLY ceiling that catches every way of splitting an archive. Before this phase the original
had per-entry ceilings only: an ``.xlsx`` reads ``sharedStrings.xml`` PLUS every ``sheetN.xml``, so split
small enough every entry fits and the total still reaches hundreds of MB.

64 MB = 3.1x headroom over 20.6 MB (largest total measured on real files). If the real baseline RSS of
production is above ~120 MB (many Zalo accounts in one process), lower this to 32-48 MB."""

TRAN_MOT_ENTRY: Final = 32 * 1024 * 1024
"""Ceiling on ONE entry: half of the total, 4.5x headroom over the largest ``document.xml`` measured (7.13
MB). No entry may eat more than half the archive budget: stops the single enormous sheet."""

TI_LE_NEN_TOI_DA: Final = 500
"""Maximum decompressed / compressed ratio. The theoretical DEFLATE ceiling is 1032:1 (RFC 1951); real OOXML
measured at most 50.2x, degenerate machine-generated files (identical rows) up to 292.9x. 500:1 sits
between 293 and 1028: 1.7x headroom over the worst legitimate case yet still catches real bombs.

NOT 100:1 as Apache POI: precedent of mass false positives on valid Excel files (Dataverse #7854,
spark-excel #231) made users switch the check off entirely: a ceiling that is too tight is worse than
none."""

TRAN_MIEN_KIEM_TI_LE: Final = 100 * 1024
"""Below this many OUTPUT bytes already decompressed (NOT the compressed input size) the ratio check is
skipped: small noisy entries (metadata, docProps...) are no threat whatever their ratio. Apache POI does
the same (``ZipSecureFile.MIN_INFLATE_RATIO``: ratio is not examined until 100 KiB of OUTPUT has been
read); this is POI's own 100 KiB, not a number of our own: a wider exemption floor (say 1 MB) would let a
bomb with the SAME ratio but only ~1,000,000 bytes of output through the zip layer.

IMPORTANT when reading the code: the exemption in ``zip_stream_entry`` compares ``byte_entry`` (counted
WHILE inflating) with this constant, NOT ``len(comp_data)``. The first version of the original phase
compared the compressed size and made the ratio check dead code (the one-entry ceiling always fired
first); it was fixed and has its own test."""

TRAN_SO_ENTRY: Final = 256
"""Maximum number of entries in an archive. Real OOXML corpus: 23.2 on average, 99 at most (2.6x
headroom). Stops archives of tens of thousands of tiny entries (cheap in bytes, costly to walk the
central directory and open streams)."""

TRAN_DO_SAU_XML: Final = 256
"""Maximum XML tag nesting depth: guards the SAX reader itself against ReDoS / stack blow-up. Measured in
the original: blocks a 4 MB adversarial input in 2.1 ms regardless of the input size (it throws as soon as
the depth is exceeded). Real Word documents rarely nest beyond ~20 levels."""

TRAN_TONG_KY_TU_TRICH: Final = 8 * 1024 * 1024
"""Ceiling on the total number of characters EXTRACTED (real text gathered into the result, not the size
of the input XML). [estimate] not measured on the largest document an operator plans to upload; tune with
``KB_MAX_FILE_MB`` if needed. Stops "valid XML that is all text", which no zip/depth ceiling catches (real
text is usually only 1-2% of the XML size, so an XML ceiling cannot stop a bomb made of many valid
``<w:t>`` without deep nesting)."""

TRAN_SO_COT_EXCEL: Final = 16384
"""Real maximum number of Excel columns (last column XFD = 16,384): ceiling for the column index derived
from the ``r=`` attribute of ``<c>`` (``xlsx_sax_sheet_builder``).

Without the clamp ``r="AAAAAAA1"`` (7 letters) maps to a column index above 321 million and the gap-filling
loop would allocate a list of that many strings. Entries with such an ``r=`` need only a few hundred bytes:
no zip/entry/total ceiling above catches it."""

TRAN_TONG_SO_O: Final = 2_000_000
"""Total number of CELLS (including padding cells created by jumping columns, not only cells with text)
allowed for the WHOLE xlsx file, one counter shared by EVERY sheet. Clamping ``TRAN_SO_COT_EXCEL`` bounds
the allocation of ONE cell, not how many ROWS repeat it: 100,000 rows each with one ``<c r="XFD1"/>``
(about 507 KB compressed) make the gap-filling loop run ~1.6 billion appends. Rows made only of EMPTY
cells are dropped before they are added to the extracted-characters counter, so
``TRAN_TONG_KY_TU_TRICH`` does not catch them: this is the SECOND ceiling, measured in allocation WORK,
for exactly that cost.

2,000,000 is about the number of REAL ``<c>`` that fit in one 32 MB entry (each ``<c r="A1" s="1"/>`` is at
least ~15-20 bytes), so it adds no restriction over the entry ceiling for real content; it only stops the
AMPLIFICATION through padding cells."""

type NguonChanTran = Literal["khai-bao", "do-that"]
"""Where the information that BLOCKED came from: ``"khai-bao"`` reads a size/count DECLARED in the central
directory (cheap, nothing inflated yet, but can be forged); ``"do-that"`` counts DIRECTLY while inflating
or processing (always true, cannot be dodged by forging)."""


class LoiVuotTran(Exception):  # noqa: N818 - original class name, kept for the port map
    """Raised when ANY ceiling above is exceeded. It marks the error so ``xml_sax_scan`` does not
    translate an already-Vietnamese error (from ``zip_stream_entry`` or from the docx/xlsx state machines)
    into a generic "XML không hợp lệ: ...". Recognised by TYPE, not by matching the message.

    ``entry_name`` / ``nguon`` are optional DIAGNOSTIC fields, NOT exposed in ``message`` (which stays
    short for the end user reading the dashboard). They live only in the extraction worker process and in
    tests: the worker flattens the error into its message before it crosses the process boundary. Nothing
    in running code reads them; tests use them to tell which ceiling fired and whether on a declared or a
    measured number."""

    def __init__(
        self,
        message: str,
        *,
        entry_name: str | None = None,
        nguon: NguonChanTran | None = None,
    ) -> None:
        super().__init__(message)
        self.entry_name = entry_name
        self.nguon = nguon
