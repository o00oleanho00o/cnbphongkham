# ported from: evals/eval-report.ts
"""Print the eval result table to the terminal.

Apart from the runner because this is pure PRESENTATION: it takes results that already exist and decides
nothing. Pure, so it is testable without running a model.

No ANSI colour codes: the table is mostly read in a Windows terminal and often pasted into reports, where
colour codes turn into noise. Text labels read just as clearly. Forced deviation: ``console.log`` becomes a
``write`` callable (default ``sys.stdout.write``) so the tests capture the table without touching stdout.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KetQuaCase:
    ten: str
    dat: bool
    tool_da_goi: list[str]
    tokens: int
    giay: float
    tra_loi: str
    """The text the user REALLY receives (after the cleaning layer)."""
    ly_do_hong: list[str] = field(default_factory=list[str])
    """Why it failed; empty when it passed."""


def _cot(s: str, n: int) -> str:
    return f"{s[: n - 1]}~" if len(s) > n else s.ljust(n)


def _stdout(line: str) -> None:
    sys.stdout.write(line + "\n")


def in_bang(kq: list[KetQuaCase], write: Callable[[str], None] = _stdout) -> None:
    write("")
    write(f"{_cot('CASE', 16)} {_cot('KẾT QUẢ', 8)} {_cot('TOOL ĐÃ GỌI', 34)} {_cot('TOKEN', 8)} GIÂY")
    write("-" * 80)
    for r in kq:
        write(
            f"{_cot(r.ten, 16)} {_cot('ĐẠT' if r.dat else 'HỎNG', 8)} "
            f"{_cot(', '.join(r.tool_da_goi) or '(không)', 34)} {_cot(str(r.tokens), 8)} {r.giay:.1f}"
        )
    write("-" * 80)

    hong = [r for r in kq if not r.dat]
    write(f"{len(kq) - len(hong)}/{len(kq)} đạt")

    for r in hong:
        write("")
        write(f"HỎNG: {r.ten}")
        for ly_do in r.ly_do_hong:
            write(f"  - {ly_do}")
        # The reply too: almost every time it has to be read to know what the model was thinking, and hunting
        # for it in the log is work
        write(f"  Bot trả lời: {json.dumps(r.tra_loi[:300], ensure_ascii=False)}")
