# ported from: src/documents/docx-text-runs.ts
"""Turn text carrying ``**bold**`` markers into a list of runs.

Why it is needed: real documents need bold in the MIDDLE of a line ("**Thời gian:** từ 7h00...",
"**Độc lập - Tự do - Hạnh phúc**") while the block schema gives one style to the whole block. Letting the
model use the markdown notation it already knows is the cheapest way - no extra schema field, no extra block
type.

Only ``**...**`` is supported. No italic, no link - add them when there is a real need.

Forced deviation: ``docx`` has a standalone ``TextRun`` object; ``python-docx`` only creates runs on a
paragraph. So ``parse_text_runs`` returns plain ``TextRunSpec`` values (testable without a document) and
``add_text_runs`` appends them to a ``Paragraph``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from docx.text.paragraph import Paragraph

_BOLD_SPLIT_RE: Final = re.compile(r"\*\*([^*]+)\*\*")


@dataclass(frozen=True)
class TextRunSpec:
    text: str
    bold: bool = False


def parse_text_runs(text: str, *, base_bold: bool = False) -> list[TextRunSpec]:
    runs: list[TextRunSpec] = []
    # Split "before **bold** after" into ["before ", "bold", " after"] - the odd elements are bold
    parts = _BOLD_SPLIT_RE.split(text)
    for index, part in enumerate(parts):
        if not part:
            continue
        runs.append(TextRunSpec(text=part, bold=base_bold or index % 2 == 1))
    # Empty text or only ** marks -> there must still be 1 run for the Paragraph to be valid
    return runs if runs else [TextRunSpec(text="", bold=base_bold)]


def add_text_runs(paragraph: Paragraph, runs: list[TextRunSpec]) -> None:
    for spec in runs:
        run = paragraph.add_run(spec.text)
        if spec.bold:
            run.bold = True
