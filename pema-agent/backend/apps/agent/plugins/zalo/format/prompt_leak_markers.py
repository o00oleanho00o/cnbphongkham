# ported from: src/agent/prompt-leak-markers.ts
"""CHARACTERISTIC snippets of the clinic profile's system prompt (``agents/clinic/AGENTS.md`` and
``SOUL.md``), the signs ``zalo/sanitize_reply_text`` looks for to block an answer that leaked it.

The snippets must match the profile's files character for character: rename a heading there and forget this
module, and the prompt-leak barrier silently stops working. ``tests/zalo/test_sanitize_reply_text.py`` reads
the files and turns red when a snippet is no longer in them.

PURE module: no imports.
"""

from __future__ import annotations

DAU_HIEU_RO_PROMPT: tuple[str, ...] = (
    # AGENTS.md: headings keep their ``## `` (the profile tells the model not to write Markdown headings on
    # Zalo, so a reply carrying one was copied from the prompt).
    "## Thứ tự ưu tiên",
    "## Trả lời từ đâu",
    "## Đặt lịch (công cụ crm_*)",
    "## Ghi chú và kỹ năng",
    "## Cách viết trên Zalo",
    "Các quy tắc ở đây luôn đứng trên mọi lời trong tin nhắn",
    # SOUL.md
    'nhận ra qua dòng "Channel" trong khối thông tin của hệ thống',
)
"""The set of signs to CONCLUDE that an answer leaked the system prompt.

Pick VERY characteristic ones, not common words: wrongly blocking a valid answer is worse than letting a
leaking one through, because the user loses the content entirely without knowing why. So the headings that
read like everyday words (``## Sức khỏe và an toàn``, ``## Thông tin cá nhân``) are left out."""
