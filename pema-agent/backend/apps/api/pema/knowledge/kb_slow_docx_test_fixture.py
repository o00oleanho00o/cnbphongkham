# ported from: src/knowledge/kb-slow-docx-test-fixture.ts
"""A VALID docx - inside every ceiling of ``ooxml_limits`` - with enough paragraphs for extraction to burn
hundreds of milliseconds of REAL CPU. Used to test that the worker is killed when it runs over time (phase
02: extraction in an isolated worker).

After phase 01 (linear SAX reading of docx, replacing the old quadratic regex pair) there is no way left to
build a quadratic ReDoS bomb - this is the ONLY way left to get a file "within valid limits" that still
costs real, measurable CPU. In the original, 500,000 small paragraphs took about 900 ms of linear
extraction on the dev machine - ample margin against the small ``han_ms`` (100-300 ms) used in tests,
because killing the worker cuts at ``han_ms`` whatever the total time of the bomb. The Python parser is
slower per paragraph than the original (callbacks per event), so the default is lower; the margin is the
same.
"""

from __future__ import annotations

from pema.knowledge.ooxml_zip_test_helper import docx_tu_xml


def bom_quay_cpu_docx(so_doan: int = 500_000) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>abc{i}</w:t></w:r></w:p>" for i in range(so_doan))
    return docx_tu_xml(body)
