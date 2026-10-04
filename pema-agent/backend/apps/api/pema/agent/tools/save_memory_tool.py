# ported from: src/agent/tools/save-memory-tool.ts
"""``save_memory``: memory layer 3 (the equivalent of the ``bio`` tool of ChatGPT): the agent decides by
itself to
store a fact worth remembering for the long term. The fact is written with the context it was learned in
(DM or
group) so the injection layer applies the asymmetric rule: a fact learned in a DM never appears in a group.

THE TOOL DESCRIPTION IS THE ONLY PLACE THAT TEACHES THE MODEL WHEN TO WRITE: no rule about memory in the
persona. Hermes chose exactly this ("Behavioral guidance lives in the tool schema description",
``tools/memory_tool.py``); keeping it in one place means there are no two copies of the guidance drifting
apart.

The first description only said what NOT to do ("only use when...", "do not store trivia") and the
measured result was: 1 fact in 92 agent turns. This one follows the structure of Hermes: it says what to
do PROACTIVELY first, with a priority order, and only then the skip list.

Forced deviations:

* ``saveMemoryFact`` / ``suaFactTheoDoanChu`` / ``xoaFactTheoDoanChu`` (synchronous SQLite) are the async
  ``MemoryStore.save_memory_fact`` of the contract and the ``MemoryEditPort`` of ``tool_deps`` (the
  contract has no edit method: gap reported to package G).
* NEW (policy, PLAN-AI01 section 5, hook ``allow_memory_write``): in ``patient_channel`` ``save_memory``
  is off for content that came from a patient and only staff write. Every action (add, edit, delete) asks
  ``PolicyHooks.allow_memory_write`` first; a refusal is a marked failure telling the model nothing was
  stored. The tool is not removed: a ``staff_assistant`` profile keeps it exactly as in zalo-agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import KetQuaLoiTool, ket_qua_loi
from pema_contracts.conversation import MemoryEditFailed, MemoryEditScope
from pema_contracts.policy import MemorySource, PolicyProfileKey
from pema_contracts.tools import ToolContext

MO_TA = "\n".join(
    [
        "Lưu điều đáng nhớ về người đang chat hoặc về nhóm, dùng lại được ở những lần trò chuyện sau.",
        "Điều đã nhớ được nhét vào MỌI lượt sau, nên viết ngắn và đúng trọng tâm.",
        "",
        "KHI NÀO: chủ động lưu ngay khi người dùng nói ra sở thích, thói quen, thông tin cá nhân,",
        "hoặc ĐÍNH CHÍNH điều bạn đang nhớ sai. Thứ tự ưu tiên: người dùng đính chính > sở thích và",
        "thông tin cá nhân > quyết định đã chốt, việc đã hứa.",
        "Trí nhớ tốt là trí nhớ khiến người ta không phải nhắc lại lần thứ hai.",
        "",
        "SỬA VÀ XÓA: nhớ sai thì dùng action 'sua' - ĐỪNG thêm điều mới chồng lên, để lại hai điều",
        "mâu thuẫn còn tệ hơn không nhớ gì. Điều chỉ đúng một lúc rồi hết (đang ốm, đang đi công tác)",
        "thì 'xoa' khi đã qua. Cả hai đều cần 'doan_chu': một đoạn chữ ngắn khớp đúng điều cũ.",
        "",
        "KHÔNG LƯU: chuyện vặt một lần, thứ hỏi lại là biết ngay, nội dung bạn vừa đọc được từ web",
        "hay từ file người khác gửi, tiến độ việc đang làm dở.",
    ]
)


class SaveMemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["them", "sua", "xoa"] = Field(
        default="them",
        description="'them' = nhớ điều mới; 'sua' = sửa điều đang nhớ sai; 'xoa' = bỏ điều không còn đúng",
    )
    content: str | None = Field(
        default=None,
        min_length=5,
        max_length=500,
        description=(
            "Nội dung cần nhớ, 1-2 câu ngắn gọn, vd 'Anh Hải thích cà phê đen, không đường'. "
            "Bắt buộc với 'them' và 'sua'."
        ),
    )
    doan_chu: str | None = Field(
        default=None,
        min_length=3,
        description=(
            "Đoạn chữ ngắn khớp đúng điều đang nhớ cần sửa/xóa, lấy từ chính nội dung đó. "
            "Bắt buộc với 'sua' và 'xoa'."
        ),
    )
    about: Literal["sender", "thread"] = Field(
        description="'sender' = về người vừa nhắn; 'thread' = về nhóm/cuộc trò chuyện này"
    )


def cau_tra_khi_hong(ket_qua: MemoryEditFailed) -> KetQuaLoiTool:
    """Answer to the model when an edit/delete does not match: say clearly what to do next.

    Lists again what is remembered exactly like Hermes does ("Check current_entries below and retry"): the
    model cannot see the ids, so a bare "no match" leaves it no way to correct itself, only to keep
    guessing."""
    if ket_qua.kind == "khop_nhieu":
        ds = "\n".join(f"- {c}" for c in ket_qua.matching_facts)
        return ket_qua_loi(
            f"Đoạn chữ đó khớp nhiều điều đang nhớ, không rõ là cái nào:\n{ds}\n"
            "Gọi lại với đoạn chữ cụ thể hơn."
        )
    if not ket_qua.existing_facts:
        return ket_qua_loi("Chưa nhớ điều gì về đối tượng này nên không có gì để sửa hoặc xóa.")
    ds = "\n".join(f"- {c}" for c in ket_qua.existing_facts)
    return ket_qua_loi(
        f"Không điều nào đang nhớ chứa đoạn chữ đó. Đang nhớ:\n{ds}\n"
        "Gọi lại với đoạn chữ lấy từ đúng danh sách trên."
    )


def create_save_memory_tool(ctx: ToolContext, deps: ToolDeps) -> FunctionTool[SaveMemoryInput]:
    account = ctx.account
    message = ctx.message

    async def handler(args: SaveMemoryInput) -> object:
        subject_id = message.sender_id if args.about == "sender" else message.thread_id
        if not subject_id:
            return ket_qua_loi("Không xác định được đối tượng để lưu")

        # Policy gate (patient_channel: only staff write what is remembered). The source is the patient
        # when the turn runs under the patient profile: the content the model wants to store came from
        # that conversation.
        source = (
            MemorySource.PATIENT_MESSAGE
            if ctx.policy.profile.key is PolicyProfileKey.PATIENT_CHANNEL
            else MemorySource.STAFF
        )
        if not await deps.policy.allow_memory_write(ctx.policy, source):
            return ket_qua_loi(
                "Kênh này không cho tự ghi nhớ nội dung từ người đang chat "
                "(chỉ nhân viên phòng khám được ghi). "
                "Chưa lưu gì - nói thật với người dùng, đừng hứa là đã nhớ."
            )

        # ``action`` always has a value here (pydantic default). The original wrote ``action ?? "them"``
        # because a direct call of ``execute`` bypassed the zod default and an empty action fell into the
        # edit branch: an empty action must mean "remember", never an error.
        hanh_dong = args.action

        if hanh_dong == "them":
            if not args.content:
                return ket_qua_loi("Thiếu nội dung cần nhớ")
            kq = await deps.memory.save_memory_fact(
                ctx.clinic_id,
                account_id=account.id,
                subject_id=subject_id,
                content=args.content,
                learned_in_thread_id=message.thread_id,
                learned_in_group=message.is_group,
            )
            # NOT an error: what must be remembered is already in memory, exactly what the model wants.
            # But say clearly that no copy was written, or the model thinks it failed and calls again.
            # Same semantics as "Entry already exists" of Hermes.
            if not kq.saved:
                return f"Điều này đã có sẵn trong trí nhớ, không ghi thêm bản trùng: {args.content}"
            return f"Đã ghi nhớ: {args.content}"

        if not args.doan_chu:
            return ket_qua_loi("Thiếu đoạn chữ để tìm điều cần sửa hoặc xóa")

        # As narrow as the set the model can SEE: in a group, what is remembered about a PERSON can only
        # be touched if it was learned right in the group. Without this the model could edit/delete facts
        # learned in a private chat, and leak them through the error message.
        scope = MemoryEditScope(
            account_id=account.id,
            subject_id=subject_id,
            only_group_learned=message.is_group and args.about == "sender",
        )

        if hanh_dong == "xoa":
            xoa = await deps.memory_edit.delete_fact_by_fragment(ctx.clinic_id, scope, args.doan_chu)
            if isinstance(xoa, MemoryEditFailed):
                return cau_tra_khi_hong(xoa)
            return f"Đã bỏ khỏi trí nhớ: {xoa.old_content}"

        if not args.content:
            return ket_qua_loi("Thiếu nội dung mới để thay vào")
        sua = await deps.memory_edit.edit_fact_by_fragment(ctx.clinic_id, scope, args.doan_chu, args.content)
        if isinstance(sua, MemoryEditFailed):
            return cau_tra_khi_hong(sua)
        return f'Đã sửa lại: "{sua.old_content}" -> "{args.content}"'

    return FunctionTool(name="save_memory", description=MO_TA, input_model=SaveMemoryInput, handler=handler)
