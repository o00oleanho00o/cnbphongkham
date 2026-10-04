# ported from: src/agent/prompt-leak-markers.ts
"""CHARACTERISTIC snippets of the internal system prompt, shared between the place that PRODUCES them
(``persona_prompt``, ``wrap_untrusted_content``) and the place that GUARDS them
(``zalo/sanitize_reply_text``).

No forced deviation.

One single source because the two sides must match character for character: edit the persona wording and
forget the guard, and the prompt-leak barrier silently stops working with nothing turning red. This is
exactly the class of bug the project already hit once with ``tool_loop_guard``.

PURE module: no imports.
"""

from __future__ import annotations

THE_NOI_DUNG_NGOAI = "noi_dung_ngoai"
"""Name of the tag wrapping external content. ``wrap_untrusted_content`` turns EVERY occurrence of this
string inside web content into ``khoi-ngoai`` before wrapping, so a web page cannot make the answer contain
it by itself - this sign can almost only come from the system prompt itself. (The replacement string is
SHORTER than the one replaced, on purpose, so the replacement does not make the string longer - see
``DANG_KHU`` in ``wrap_untrusted_content``.)

Known exception: a user types this string straight into Zalo and the bot parrots it back. Accept blocking
that case wrongly - someone typing the exact name of an internal tag is probing, not chatting."""

THE_DIEU_DA_NHO = "dieu_da_nho"
"""Name of the tag wrapping the "remembered facts" block in the system prompt.

Why memory also needs a boundary: it is ONE of the two DURABLE prompt-injection paths (the other is the
rolling summary of the thread - ``THE_BOI_CANH``). Web content is already wrapped in
``THE_NOI_DUNG_NGOAI``, messages from outside the allowlist already carry the "[chưa xác minh]" label - but
a fact goes straight into the system prompt as a bare bullet and sits there on EVERY later turn. A cleverly
written message that lures the model into saving an instruction as a memory plants a permanent command.
Both durable paths are now wrapped.

``khoiDieuDaNho`` removes every occurrence of this string from the fact content before wrapping, exactly
like ``wrap_untrusted_content`` does - otherwise writing the exact closing tag into a fact would cut the
boundary short."""

THE_BOI_CANH = "boi_canh_da_chot"
"""Name of the tag wrapping the "settled context" block (rolling summary of the thread) in the system
prompt. The SAME reason as ``THE_DIEU_DA_NHO``: a summary produced by an LLM FROM strangers' messages then
sits in the system prompt on EVERY later turn - an identical durable injection path, NOT any less (it used
to be pasted bare, unwrapped). ``khoiBoiCanhThread`` removes every occurrence of this string from the
summary content before wrapping."""

TIEU_DE_QUY_TAC_AN_TOAN = "Quy tắc an toàn (tuyệt đối, không có ngoại lệ):"
"""Heading of the safety section in ``BASE_PERSONA``."""

TIEU_DE_KHA_NANG = "Khả năng của bạn lúc này"
"""Opening of the tool listing section, produced per turn by ``persona_prompt``.

ONLY a piece to assemble, NOT used as a leak sign - see ``DAU_HIEU_RO_PROMPT``."""

KHA_NANG_DAY_DU: tuple[str, ...] = (
    f"{TIEU_DE_KHA_NANG} (đúng những công cụ đang bật",
    f"{TIEU_DE_KHA_NANG}: KHÔNG có công cụ nào",
)
"""The two FULL sentences that ``persona_prompt`` really produces from ``TIEU_DE_KHA_NANG``.

Must guard with the full sentence and not ``TIEU_DE_KHA_NANG`` alone: that short string is everyday
Vietnamese, and the persona only uses a name WHEN it knows the name so the bot still says "bạn" a lot.
"Khả năng của bạn lúc này đã đủ để thi B1 rồi ạ" is a perfectly valid answer that hits the sign - heavy
consequence and no self-recovery: the user loses the answer ENTIRELY, and asking again changes nothing
because the model regenerates exactly that phrasing."""

DAU_HIEU_RO_PROMPT: tuple[str, ...] = (
    f"<{THE_NOI_DUNG_NGOAI}",
    # Same reason and same level of safety as the tag above: the ``<`` in front means nobody writes it by
    # accident while chatting. The fact content has had the tag name removed at wrapping time, so the model
    # cannot read the underscore form from this very block.
    f"<{THE_DIEU_DA_NHO}",
    # Same level of safety: the ``<`` in front means nobody types it by accident; the summary content has
    # had the tag name removed at wrapping time.
    f"<{THE_BOI_CANH}",
    TIEU_DE_QUY_TAC_AN_TOAN,
    *KHA_NANG_DAY_DU,
)
"""The set of signs to CONCLUDE that an answer leaked the system prompt.

Pick VERY characteristic ones, not common words: wrongly blocking a valid answer is worse than letting a
leaking one through, because the user loses the content entirely without knowing why. None of the strings
here is something anyone writes by accident while messaging normally."""
