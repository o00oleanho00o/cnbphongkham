# Office fixtures - frozen, do not regenerate

Copied from the zalo-agent test fixtures (`src/knowledge/fixtures`, MIT, see `THIRD_PARTY_NOTICES.md`). They were
written by REAL Microsoft Word/Excel, which is the point: the tests of `extract_docx_text` / `extract_xlsx_text`
reach edge cases that only real Office writes (tab stops in `w:pPr`, empty self-closing cells, self-closing
`<w:p/>`), not the files a library generates.

| File | Content | Edge case it proves |
|---|---|---|
| `word-tabstop.docx` | the paragraph "Ca phe" with 2 tab stop definitions in `w:pPr><w:tabs>` and 2 real tabs in `w:r` | a tab stop must not leak as raw XML; a real tab stays a tab |
| `word-table.docx` | a paragraph with `xml:space="preserve"`, a 2x2 table (row 2 has 2 empty self-closing `<w:p/>` cells) and one more `<w:p/>` at the end | table row structure kept; self-closing `<w:p/>` does not merge paragraphs |
| `excel-o-rong-co-dinh-dang.xlsx` | "Mon / (empty, formatted) / Gia" and "Ca phe / (empty) / 25000" | a self-closing empty cell `<c r="B1" s="1"/>` must not swallow the next cell nor leak a sharedString index |

Content is invented test text (unaccented words on purpose: the bytes Word/Excel wrote).

ONE change from the originals: the author name in `docProps/core.xml` (`dc:creator`, `cp:lastModifiedBy`) was
replaced by "Synthetic Author", because no real name may sit in this repository. Every other entry of each
archive is byte for byte the original (`document.xml`, `sheet1.xml`, `sharedStrings.xml`, ...), and nothing the
tests read was touched. Do not regenerate them: Office is not byte-deterministic.
