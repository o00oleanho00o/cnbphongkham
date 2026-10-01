"""The real seams of the eval runner (package G, no TS source): D4's tools and C2's reply formatting.

``run_eval.EvalWiring`` was written when only the engine existed, so its defaults were a canned tool set
and no formatting at all (the formatting cases FAILED on purpose). With the packages merged the runner can
measure
what the real system does:

* ``real_registry``: the tool catalogue and registry of package D4 (``DefaultToolRegistry``) over the fake
  stores of ``pema.agent.tools.testing``. The tool BODIES are the real ones (``get_datetime``, ``web_search``,
  ``save_memory`` ... with the real argument validation and failure results); only the stores behind them are
  in-memory, so a run touches no database and no channel;
* ``real_format_reply``: what the channel does to the text of a reply before it leaves: the leak guard and the
  markdown clean-up (``prepare_outgoing_text``, the same two steps as the chat turn and the scheduler) and the
  translation of markdown into Zalo style spans (``markdown_to_zalo_styles``), so the formatting cases measure
  the real thing.

``real_wiring`` combines them; ``python -m evals.run_eval`` uses it by default.
"""

from __future__ import annotations

from evals.eval_formatting_view import SentMessage, ZaloStyle
from pema.agent.tools.testing import make_tool_deps
from pema.agent.tools.tool_registry import DefaultToolRegistry
from pema.channels.prepare_outgoing_text import dinh_dang_neu_bat, lam_sach_theo_cau_hinh
from pema_contracts.tools import ToolRegistry


def real_registry() -> ToolRegistry:
    """D4's registry over fake stores (the tool bodies are real)."""
    return DefaultToolRegistry(make_tool_deps())


def real_format_reply(text: str) -> list[SentMessage]:
    """The reply as the channel would send it: a blocked text goes nowhere (an empty list), the others become
    one message with its style spans."""
    clean = lam_sach_theo_cau_hinh(text)
    if clean.chan or not clean.text.strip():
        return []
    formatted = dinh_dang_neu_bat(clean.text)
    styles = [ZaloStyle(start=s.start, len=s.length, st=s.style) for s in formatted.styles]
    return [SentMessage(msg=formatted.text, styles=styles)]
