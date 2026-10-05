# ported from: src/server/routes/kb-route-guards.ts (the file signature part)
"""Real signature of an uploaded file (magic bytes) - NOT trusting the extension. Lives in the knowledge
package, and ``pema.api.kb_route_guards`` re-exports it, because the store must be able to check it too (an
agent-side package may not import ``pema.api``) and a second check inside the store is the defence in depth
for any caller that is not the route.

The extension is what the user claims; the first bytes are what the operating system/library reads. txt/md
have no fixed signature so they are not checked (any byte is accepted).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from pema.knowledge.doc_text_extract import DinhDangKb

MAGIC_BYTES: Final[dict[str, Callable[[bytes], bool]]] = {
    "pdf": lambda buf: buf[:4].decode("latin-1") == "%PDF",
    "docx": lambda buf: buf[:2].decode("latin-1") == "PK",
    "xlsx": lambda buf: buf[:2].decode("latin-1") == "PK",
}


def khop_chu_ky_that(buf: bytes, dinh_dang: DinhDangKb) -> bool:
    kiem_tra = MAGIC_BYTES.get(dinh_dang)
    return kiem_tra(buf) if kiem_tra is not None else True
