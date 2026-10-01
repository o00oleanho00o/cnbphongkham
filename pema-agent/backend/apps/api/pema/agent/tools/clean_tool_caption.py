# ported from: src/agent/tools/clean-tool-caption.ts
"""Clean the CAPTION written by the model before it becomes a real chat message.

Forced deviation: ``lamSachTraLoi`` / ``lamSachGiuDinhDang`` (``sanitize-reply-text.ts``) and
``markdownSangStyleZalo`` (``markdown-to-zalo-styles.ts``) belong to package C2, so they come in as the
``ReplyTextCleaner`` and ``MarkdownStyler`` ports of ``ToolDeps`` (the functions below take them as
arguments instead of importing them). Styles are the contract ``TextStyle`` (offsets in UTF-16 units like
zca-js).

The four tools that send a file/image (``send_file``, ``create_word_document``, ``create_excel_file``,
``create_image``) all called ``api.sendMessage`` with ``msg: caption``. That is the text of the MODEL
going down to Zalo without any cleaning layer: exactly the detour that ``tag_member`` had been plugged
against, only these four places were missed in the previous round.

Concrete consequence: the model sends a file with the caption ``**Báo giá tháng 8** - xem [chi
tiết](https://...)`` and the user receives the markdown characters verbatim.

Different from ``tag_member`` in the BLOCK branch: the caption is only an accompanying note, while the
file is already built and about to go. Blocking the whole turn because of one caption line throws away the
heaviest part of the work, so here only the caption is DROPPED and the file is still sent: the user still
gets what they need."""

from __future__ import annotations

from dataclasses import dataclass, field

from pema.agent.tools.tool_deps import MarkdownStyler, ReplyTextCleaner
from pema.config.runtime_tuning_settings import get_tuning_bool
from pema_contracts.channel import TextStyle


@dataclass(frozen=True)
class TinKemFile:
    """``{ msg, styles? }``: ``styles`` is empty when there is nothing to style (the original left it
    undefined)."""

    msg: str
    styles: list[TextStyle] = field(default_factory=list[TextStyle])


def cap_tion_sach(caption: str | None, cleaner: ReplyTextCleaner) -> str | None:
    """``capTionSach``: the caption cleaned of markdown, or ``None`` when it leaks internals (then
    dropped)."""
    if caption is None or not caption.strip():
        return caption

    sach = cleaner.clean_reply(caption)
    if sach.blocked:
        return None
    return sach.text.strip() or None


def tin_kem_file(caption: str | None, cleaner: ReplyTextCleaner, styler: MarkdownStyler) -> TinKemFile:
    """Message part of one send with a file: cleaned text + Zalo styles.

    Why the caption is styled too: it is a REAL ZALO MESSAGE like any other, and the caption is exactly
    where numbers that need emphasis appear ("Báo giá **tháng 8**"). Skipping it would leave the
    attachment as the only message with flat text.

    Does NOT split into several parts here: the caption must travel in the same trip as the attachment,
    splitting would drop the file out of the message that has the text. The caption is short anyway, so no
    worry."""
    if not get_tuning_bool("ZALO_RICH_TEXT_ENABLED"):
        return TinKemFile(msg=cap_tion_sach(caption, cleaner) or "")
    if caption is None or not caption.strip():
        return TinKemFile(msg="")

    sach = cleaner.clean_keep_formatting(caption)
    if sach.blocked:
        return TinKemFile(msg="")

    styled = styler.markdown_to_styles(sach.text)
    chu = styled.text.strip()
    if not chu:
        return TinKemFile(msg="")
    # The ``.strip()`` above shifts the text, so the offsets are right only when nothing was cut at either
    # end: attach the styles only then. The model's caption is almost always clean at both ends; in the
    # rare other case the formatting is lost rather than painting the wrong place.
    if chu == styled.text and styled.styles:
        return TinKemFile(msg=chu, styles=styled.styles)
    return TinKemFile(msg=chu)
