# ported from: evals/fake-zalo-api.ts
"""FAKE Zalo API for the evals.

THIS IS THE MOST IMPORTANT SAFETY BARRIER OF THE WHOLE EVAL SUITE. The engine hands the ``action`` tools
(``send_file``, ``tag_member``, ``add_reaction``, ``create_image``, ``create_word_document``,
``create_excel_file``) a channel to send through, and running the evals against a real channel means the bot
messages real people. That is not a theoretical risk, it is the default behaviour if the injection is
forgotten.

Every function RECORDS the call and returns a valid empty value, so the runner can assert "did anything go
out" and not only "which tool was called".

Forced deviation: the original fakes the zca-js ``API`` object; the port fakes the same five calls under
Python names and the runner registers a ``pema_contracts.testing.FakeChannel`` in the channel registry, so
nothing in the eval process holds a real channel either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evals.eval_formatting_view import SentMessage, ZaloStyle


@dataclass(frozen=True)
class LoiGoiApi:
    ham: str
    tham_so: tuple[object, ...]


@dataclass
class FakeZaloApi:
    loi_goi: list[LoiGoiApi] = field(default_factory=list[LoiGoiApi])
    """Every call recorded, in order."""
    tin_da_gui: list[str] = field(default_factory=list[str])
    """Text of the messages that were "sent": used to assert the evals do not message anyone outside."""
    tin_kem_dinh_dang: list[SentMessage] = field(default_factory=list[SentMessage])
    """Messages WITH formatting, exactly the payload that went into ``send_message``.

    Apart from ``tin_da_gui`` so what already uses it stays untouched, but this is what measures presentation
    quality: ``tin_da_gui`` is the bare text after translation, where the ``**`` markers are gone and there is
    no way to know whether anything was bold."""

    def _ghi(self, ham: str, *tham_so: object) -> None:
        self.loi_goi.append(LoiGoiApi(ham=ham, tham_so=tham_so))

    def get_own_id(self) -> str:
        return "eval-self"

    async def send_message(
        self, msg: str, thread_id: str, thread_type: int, styles: list[ZaloStyle] | None = None
    ) -> dict[str, str]:
        self._ghi("sendMessage", msg, thread_id, thread_type, styles)
        self.tin_da_gui.append(msg)
        self.tin_kem_dinh_dang.append(SentMessage(msg=msg, styles=list(styles or [])))
        n = len(self.tin_da_gui)
        return {"msgId": f"eval-{n}", "cliMsgId": f"c-{n}"}

    async def add_reaction(self, icon: object, target: object) -> dict[str, Any]:
        self._ghi("addReaction", icon, target)
        return {}

    async def send_typing_event(self, thread_id: str, thread_type: int) -> dict[str, Any]:
        self._ghi("sendTypingEvent", thread_id, thread_type)
        return {}

    async def send_seen_event(self, *args: object) -> dict[str, Any]:
        self._ghi("sendSeenEvent", *args)
        return {}

    async def get_group_info(self, thread_id: str) -> dict[str, Any]:
        self._ghi("getGroupInfo", thread_id)
        # The minimal shape ``get_group_info`` of the tool set reads
        return {"gridInfoMap": {thread_id: {"name": "Nhóm eval", "totalMember": 2, "memVerList": []}}}

    def xoa_ghi_chep(self) -> None:
        self.loi_goi.clear()
        self.tin_da_gui.clear()
        self.tin_kem_dinh_dang.clear()


def tao_fake_zalo_api() -> FakeZaloApi:
    return FakeZaloApi()
