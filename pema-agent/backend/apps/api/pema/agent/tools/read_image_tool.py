# ported from: src/agent/tools/read-image-tool.ts
"""``read_image``: the "look again" tool for images, the last piece of the vision system (pattern
``read_image`` of GoClaw / ``vision_analyze`` of Hermes). The cached description is produced BEFORE the
question is known, so it is lossy: "count the yellow fish" needs the eye asked again with a prompt that is
exactly the question. The agent decides by itself when the ready description is not enough.

Only enters the schema when the sidecar is configured (``available`` of the catalogue).

Forced deviations:

* ``getRecentMessages`` / ``loadStoredImage`` / ``askAboutImage`` (synchronous module functions) are
  ``deps.history`` (async), ``deps.stored_images`` (async) and ``deps.vision`` (async), so
  ``collect_recent_image_paths`` is async and takes ``deps``;
* the original injected ``ask`` for tests; here ``ask`` is an optional parameter that defaults to
  ``deps.vision.ask_about_image``.

Policy (new, PLAN-AI01 section 5): in ``patient_channel`` a photo sent by a patient is only FLAGGED in the
Inbox for a person, never analysed. The registry already removes ``read_image`` in that profile; this tool
also refuses by itself when the profile says ``inbound_media = FLAG_AND_HAND_OFF``, BEFORE any path is
read and before the vision port is touched (second lock: if the key is ever re-enabled by a
misconfiguration, the photo still does not leave the clinic)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.tool_deps import StoredImage, ToolDeps
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema_contracts.policy import InboundMediaAction
from pema_contracts.tools import ToolContext

RECENT_IMAGE_LIMIT = 10
"""Ceiling of the recent images the agent can choose through ``imageIndex``. A self-imposed policy: wide
enough for "the 3rd image counting from the bottom", narrow enough that the model does not have to count
by guessing in a long list. No file is read until the model chooses, so this ceiling costs nothing."""

DESCRIPTION = (
    "Nhìn kỹ lại ảnh đã nhận trong hội thoại bằng model đọc ảnh, với một câu hỏi cụ thể "
    "(đếm số lượng, đọc chữ nhỏ, xác định chi tiết, so sánh màu sắc). "
    "Dùng khi mô tả ảnh sẵn có trong hội thoại không đủ chi tiết để trả lời người dùng."
)

type AskAboutImage = Callable[[StoredImage, str], Awaitable[str]]


class ReadImageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    question: str = Field(
        min_length=1,
        description='Câu hỏi cụ thể về ảnh, vd "Đếm chính xác số cá màu vàng trong ảnh"',
    )
    image_index: int = Field(
        default=1,
        ge=1,
        le=RECENT_IMAGE_LIMIT,
        alias="imageIndex",
        description="Ảnh thứ mấy tính từ MỚI NHẤT (1 = ảnh mới nhất trong hội thoại)",
    )


async def collect_recent_image_paths(ctx: ToolContext, deps: ToolDeps) -> list[str]:
    """Gather the paths of the images, NEWEST FIRST: the batch of the current turn, then the history.
    Exposed on its own so tests need not build the tool.

    The batch is NOW ALSO in history (the message is written the moment it is received), so walking the
    batch first and then dropping duplicates is how the order "newest first" is kept without counting one
    image twice."""
    paths: list[str] = []
    for message in reversed(ctx.batch):
        for image in message.images:
            if image.local_path:
                paths.append(image.local_path)
    history = await deps.history.get_recent_messages(ctx.clinic_id, ctx.account.id, ctx.message.thread_id)
    for stored in reversed(history):
        paths.extend(stored.images)
    # DROP DUPLICATES: since the user's message is written right when it is received, the images of the
    # running batch sit in BOTH sources above. Without the filter "image 2" is again image 1, and every
    # old image is pushed back one step: whatever number the model chooses misses.
    return list(dict.fromkeys(paths))[:RECENT_IMAGE_LIMIT]


def create_read_image_tool(
    ctx: ToolContext, deps: ToolDeps, ask: AskAboutImage | None = None
) -> FunctionTool[ReadImageInput]:
    """``ask`` can be injected so tests do not touch the real network."""
    ask_fn: AskAboutImage = ask if ask is not None else deps.vision.ask_about_image

    async def handler(args: ReadImageInput) -> object:
        if ctx.policy.profile.inbound_media is InboundMediaAction.FLAG_AND_HAND_OFF:
            return ket_qua_loi(
                "Kênh này không cho phân tích ảnh của khách: ảnh đã được gắn cờ trong hộp thư để nhân viên "
                "xem. Nói với khách là nhân viên phòng khám sẽ xem ảnh và phản hồi, đừng đoán nội dung ảnh."
            )
        paths = await collect_recent_image_paths(ctx, deps)
        if not paths:
            return ket_qua_loi("Không có ảnh nào trong hội thoại gần đây để xem.")
        index = args.image_index
        rel_path = paths[index - 1] if index - 1 < len(paths) else None
        if rel_path is None:
            return ket_qua_loi(f"Hội thoại chỉ còn {len(paths)} ảnh gần đây - imageIndex {index} vượt quá.")
        image = await deps.stored_images.load_stored_image(rel_path)
        if image is None:
            return ket_qua_loi("Ảnh này đã bị dọn khỏi bộ nhớ (quá hạn lưu trữ), không xem lại được nữa.")
        try:
            answer = await ask_fn(image, args.question)
        except Exception as err:
            # Return a message for the model to interpret, do not raise into the agent loop: same rule as
            # web_search (a failing provider must not kill the whole turn)
            return ket_qua_loi(
                f"Hệ thống đọc ảnh đang lỗi ({err}). Nói thật với người dùng là chưa xem kỹ được ảnh, "
                "đừng đoán nội dung."
            )
        return answer or ket_qua_loi("Model đọc ảnh không trả lời được câu hỏi này.")

    return FunctionTool(
        name="read_image", description=DESCRIPTION, input_model=ReadImageInput, handler=handler
    )
