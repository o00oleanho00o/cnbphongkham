# ported from: src/agent/tools/tool-catalog-action.ts
"""The "action" group of the tool catalogue: send or change something on the chat.

Split from ``tool_catalog`` the way the original split by GROUP (see ``tool_catalog_read``).

``runs_in_scheduled_turn=False`` for nine of them plus ``read_image`` (kept in ``tool_catalog_read``); the
reasons are in the contract docstring of ``ToolSpec.runs_in_scheduled_turn`` and repeated at each tool
below.

Forced deviation: settings (image generation configured, scheduler enabled) were module singletons; the
tuning goes through ``get_tuning_bool`` and the image settings through ``runtime_image_settings``, both
synchronous snapshots. Which of these tools the ``patient_channel`` profile switches off is DATA in
``pema.agent.tools.tool_policy_tags`` (and ``PolicyProfile.disabled_tool_keys``); nothing is removed here.
"""

from __future__ import annotations

from pema.agent.tools.add_reaction_tool import create_add_reaction_tool
from pema.agent.tools.create_document_tools import create_excel_file_tool, create_word_document_tool
from pema.agent.tools.create_image_tool import create_image_tool
from pema.agent.tools.save_memory_tool import create_save_memory_tool
from pema.agent.tools.schedule_task_tool import create_schedule_task_tool
from pema.agent.tools.send_file_tool import create_send_file_tool
from pema.agent.tools.tag_member_tool import create_tag_member_tool
from pema.agent.tools.tai_video_tool import create_tai_video_tool
from pema.agent.tools.tool_deps import ToolDeps
from pema.config.runtime_image_settings import is_image_gen_configured
from pema.config.runtime_tuning_settings import get_tuning_bool
from pema_contracts.tools import ToolGroup, ToolSpec


def action_tool_definitions(deps: ToolDeps) -> list[ToolSpec]:
    return [
        ToolSpec(
            key="add_reaction",
            label="Thả cảm xúc",
            description="Thả reaction (tim, like...) vào tin nhắn trong hội thoại",
            group=ToolGroup.ACTION,
            # Not boasted: this is politeness during the chat, not something someone asks the bot to do.
            counts_as_capability=False,
            # A scheduled turn has no real message (empty msgId) to react to
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_add_reaction_tool(ctx),
        ),
        ToolSpec(
            key="send_file",
            label="Gửi file",
            description="Gửi file từ kho shared-files hoặc tải từ URL công khai rồi gửi",
            group=ToolGroup.ACTION,
            # Sends straight through the per-thread queue (NOT the daily cap): in a scheduled turn it would
            # bypass ``SCHEDULER_MAX_PROACTIVE_PER_DAY`` entirely, because the cap counter only grows on the
            # ``deliverProactively`` / ``reserveProactiveSlot`` road of the scheduler. Removed from scheduled
            # turns until this tool goes through the proper cap-counting road (later round).
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_send_file_tool(ctx, deps),
        ),
        ToolSpec(
            key="create_word_document",
            label="Tạo file Word",
            description="Soạn nội dung thành file .docx (tiêu đề, đoạn văn, gạch đầu dòng, bảng) rồi gửi luôn",  # noqa: E501
            group=ToolGroup.ACTION,
            # Same reason as ``send_file`` for ``runs_in_scheduled_turn=False``: sends straight, dodges the
            # daily cap.
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_word_document_tool(ctx, deps),
        ),
        ToolSpec(
            key="create_excel_file",
            label="Tạo file Excel",
            description="Soạn bảng số liệu thành file .xlsx có công thức tính sẵn rồi gửi luôn",
            group=ToolGroup.ACTION,
            # Same reason as ``send_file``.
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_excel_file_tool(ctx, deps),
        ),
        ToolSpec(
            key="create_image",
            label="Vẽ ảnh AI",
            description=(
                "Vẽ ảnh mới hoặc sửa ảnh người dùng vừa gửi (đổi màu, xóa vật thể, đổi phong cách) rồi gửi luôn"  # noqa: E501
            ),
            group=ToolGroup.ACTION,
            has_settings=True,
            available=lambda _scope: is_image_gen_configured(),
            unavailable_hint="Bấm Settings để cấu hình endpoint + model vẽ ảnh",
            # Same reason as ``send_file``: sends 2 messages ("đang vẽ..." then the image) straight
            # through the queue, dodging the daily cap. The heaviest of these five: a job "every 5
            # minutes" + prompt "draw an image then [SILENT]" produces hundreds of proactive messages a
            # day that the cap can never stop.
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_image_tool(ctx, deps),
        ),
        ToolSpec(
            key="tai_video",
            label="Tải video TikTok/Facebook",
            description="Người dùng dán link TikTok hoặc Facebook, bot tải bản không watermark rồi gửi lại",
            group=ToolGroup.ACTION,
            # Same reason as ``send_file``: sends straight, dodging the daily cap. Heavier still: a job
            # "download a video every 5 minutes" is the shortest road to losing the Zalo account.
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_tai_video_tool(ctx, deps),
        ),
        ToolSpec(
            key="tag_member",
            label="Tag thành viên",
            description="Nhắc tên (@mention) thành viên trong nhóm khi trả lời",
            group=ToolGroup.ACTION,
            # Same reason as ``send_file``.
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_tag_member_tool(ctx, deps),
        ),
        ToolSpec(
            key="save_memory",
            label="Ghi nhớ lâu dài",
            description="Tự lưu fact về người dùng/nhóm để nhớ qua các phiên chat sau",
            group=ToolGroup.ACTION,
            # The road of web content into permanent memory is a real prompt injection, and a scheduled turn
            # has no utterance of a user to learn from anyway
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_save_memory_tool(ctx, deps),
        ),
        ToolSpec(
            key="schedule_task",
            label="Lịch hẹn",
            description=(
                "Đặt/xem/sửa/hủy lịch để bot tự nhắn lại đúng cuộc trò chuyện này ở một mốc giờ trong tương lai"  # noqa: E501
            ),
            group=ToolGroup.ACTION,
            # Switch the whole schedule feature off (the tick loop no longer runs) and the tool leaves the
            # schema too: creating a new job then is pointless, nothing would pick it up to run
            available=lambda _scope: get_tuning_bool("SCHEDULER_ENABLED"),
            unavailable_hint='Bật "Bật lịch hẹn" trong Cấu hình > Lịch hẹn để dùng tool này',
            # Rule number 1 of Hermes: a job must not breed jobs
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_schedule_task_tool(ctx, deps),
        ),
    ]
