# ported from: src/agent/batch-to-user-lines.ts
"""The TEXT part of the current turn: ONE LINE PER MESSAGE ``[08/08 00:12] Hải: nội dung``, exactly the
shape ``history_to_model_messages`` builds for the history (same ``dong_tin_nguoi_dung`` function).

Forced deviation: ``ParsedMessage`` is the contract ``InboundMessage``; ``sentAt`` is an aware datetime.

Split from ``agent_turn_content`` along the line of the work: that file takes care of IMAGES (4 modes
native/describe/hybrid/blind), this one takes care of TEXT.

The old version was flat: join all the text with ``\\n`` and paste ONE name - the name of the LAST message
of the batch. Two things broke because of that:

  1. No time label, so the newest time the model saw was always the one of the message BEFORE in the
     history. The night of 07 into 08/08/2026 the model read the 23:37 label and thought the question at
     00:12 was sent the day before.
  2. Back then ``enqueueMessage`` batched per THREAD and not per sender, so in a group two people who
     @mentioned the bot in the same beat landed in one batch and the first person's words were attributed
     to the second. Now the queue locks on ``(thread, sender)`` so one batch has one person - this reason
     is NO LONGER valid, but building line by line is kept: it is still right, and it is what keeps the
     shape equal to the history (next point).

The name is pasted in a PRIVATE chat too and not only in a group - also to match the history, which always
pastes the name when it has one. Because they match, the same message renders identically on this turn and
on the next (when it has become history), so the common prefix between two requests is not cut right there.

NO ``[chưa xác minh]`` label: every message that reaches here has already passed ``shouldRespond``, i.e.
it is inside the allowlist. That label only means something for passive-listen messages, and those go the
history route only.
"""

from __future__ import annotations

from collections.abc import Sequence

from pema.agent.user_message_line import dong_tin_nguoi_dung
from pema.config.runtime_tuning_settings import bot_time_zone
from pema_contracts.channel import InboundMessage

CHI_CO_ANH = "(gửi ảnh, không kèm chữ)"
"""A message with only images still needs text, otherwise the model reads an empty line."""


def dong_tin_cua_luot(batch: Sequence[InboundMessage]) -> str:
    time_zone = bot_time_zone()
    dong: list[str] = []
    for m in batch:
        chu = m.text.strip()
        if not chu and len(m.images) == 0:
            continue
        line = dong_tin_nguoi_dung(
            created_at=m.sent_at,
            time_zone=time_zone,
            sender_name=m.sender_name,
            noi_dung=chu or CHI_CO_ANH,
        )
        if line:
            dong.append(line)

    # An empty batch does not happen on the real path (``shouldRespond`` already dropped messages with no
    # processable content), but returning an empty string here sends the model an empty text part - saying
    # it out loud beats letting it guess.
    return "\n".join(dong) if len(dong) > 0 else CHI_CO_ANH
