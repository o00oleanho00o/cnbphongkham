# ported from: src/agent/tools/create-image-tool.ts
"""``create_image``: draw a new image or EDIT the image the user just sent, then send it into the
conversation.

Notice before drawing: measured ~70 seconds per image. Staying silent that long makes the sender think the
bot ignores them and message again: annoying and it breeds one more turn. The notice is only sent AFTER
the ceiling and configuration checks, so it never makes an empty promise.

Send the image with the EXACT extension the provider returned: zca-js routes by extension, only
jpg/jpeg/png/webp take the photo_original road and show up as an IMAGE in the chat; a wrong extension
turns it into an attachment that needs a tap to download.

``generate`` is injectable so tests touch no network and cost no money.

Forced deviations:

* ``api.sendMessage`` + ``withNamedTempFile`` + ``guiFileKemCaption`` become ``send_plain_text`` (the
  notices) and ``gui_file_kem_caption(as_image=True)`` (the image bytes go straight through
  ``MediaChannel.send_image``);
* ``loadStoredImage`` / ``collectRecentImagePaths`` are the async ``deps.stored_images`` / ``deps.history``;
* the Python model-facing names ``imageIndex`` and ``transparentBackground`` are kept as aliases.

Policy: image generation sends the prompt to a third party and is one of ``MEDIA_AND_WEB_TOOL_KEYS``: the
registry removes it in ``patient_channel``. The feature itself is intact for ``staff_assistant``.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.create_image_tool_description import CREATE_IMAGE_DESCRIPTION
from pema.agent.tools.draw_image_with_one_retry import ve_voi_mot_lan_thu_lai
from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.read_image_tool import collect_recent_image_paths
from pema.agent.tools.send_attachment_with_caption import MediaSendError, gui_file_kem_caption
from pema.agent.tools.sent_by_tool_note import ghi_chu_da_gui_anh, ghi_chu_da_gui_chu
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import KetQuaLoiTool, ket_qua_loi
from pema.agent.tools.tool_send import send_plain_text, thread_key_of
from pema.config.runtime_image_settings import is_image_gen_configured
from pema.images.image_generation_client import (
    GeneratedImage,
    GenerateImageParams,
    RefImage,
    generate_image,
)
from pema.images.image_rate_limit import check_image_rate_limit
from pema.shared.logger import create_logger
from pema_contracts.tools import ToolContext

log = create_logger("create-image")

DELIVERED_NOTE = "Đã vẽ và GỬI ảnh cho người dùng rồi. KHÔNG gọi send_file để gửi lại ảnh này."

TIN_THU_LAI = "Lần vẽ đầu chưa ra ảnh, mình vẽ lại lần nữa, đợi thêm 1-3 phút nhé..."
"""Notice when the first drawing missed and the provider is called again.

Says PLAINLY that the first one did not come out rather than mumbling "still processing": the user has
already waited more than two minutes, hiding it leaves the second wait with no explanation. Repeats the
time frame because the promise "1-3 minutes" at the start of the turn has expired."""

MAX_PROMPT_CHARS = 4000
"""Prompt character ceiling. A SELF-IMPOSED POLICY, NOT a provider limit (the real limit is not measured).
Reference point: a 700 character prompt copying an article verbatim gave an e-magazine as intended, so
4000 is several times wider than the usual need while still stopping the model from pouring a whole long
document in. Above the ceiling the schema reports the error for the model to shorten it, no silent
cutting."""

TIN_DANG_VE = "Đang vẽ ảnh, đợi 1-3 phút nhé..."
TIN_DANG_SUA = "Đang sửa ảnh, đợi 1-3 phút nhé..."
# "1-3 minutes" and not "1 minute": measured 60 seconds for a normal image, 135 seconds for a text-heavy page.
# Promising 1 minute is an unkept promise.

type Generate = Callable[[GenerateImageParams], Awaitable[GeneratedImage]]


class CreateImageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: Literal["ve_moi", "sua_anh_da_gui"] = Field(
        description=(
            'BẮT BUỘC chọn. "ve_moi" = vẽ ảnh hoàn toàn mới từ mô tả (dùng cho hầu hết yêu cầu: poster, banner, '  # noqa: E501
            'e-magazine, minh họa). "sua_anh_da_gui" = CHỈ khi người dùng đã gửi ảnh trong hội thoại và nhờ sửa '  # noqa: E501
            "chính tấm đó (đổi màu, xóa vật thể, đổi phong cách)"
        )
    )
    prompt: str = Field(
        min_length=1,
        max_length=MAX_PROMPT_CHARS,
        description="Mô tả chi tiết ảnh cần vẽ, hoặc thay đổi cần thực hiện nếu đang sửa ảnh",
    )
    image_index: int | None = Field(
        default=None,
        ge=1,
        alias="imageIndex",
        description=(
            'Chỉ có tác dụng khi mode = "sua_anh_da_gui": sửa ảnh thứ mấy tính từ mới nhất. '
            "Bỏ trống = ảnh mới nhất"
        ),
    )
    transparent_background: bool | None = Field(
        default=None,
        alias="transparentBackground",
        description="Cần nền trong suốt (logo, sticker, icon để ghép lên nền khác)",
    )
    caption: str | None = Field(default=None, description="Lời nhắn gửi kèm ảnh")


def create_image_tool(
    ctx: ToolContext, deps: ToolDeps, generate: Generate = generate_image
) -> FunctionTool[CreateImageInput]:
    async def send_notice(text: str) -> None:
        """A notice that fails must not kill the drawing; it enters history only when it was really sent."""
        try:
            result = await send_plain_text(ctx, deps, text)
        except Exception:
            return
        if isinstance(result, dict):
            return
        if ctx.record_sent is not None:
            # The notice is a REAL message people read: it enters history like any other, or the dashboard
            # shows the image without its lead-in sentence.
            ctx.record_sent(ghi_chu_da_gui_chu(text))

    async def handler(args: CreateImageInput) -> object:
        thread_key = thread_key_of(ctx)

        if not is_image_gen_configured():
            return ket_qua_loi(
                "Tool vẽ ảnh chưa cấu hình (thiếu base URL, model hoặc API key). "
                "Nói thật với người dùng là chưa vẽ được."
            )

        # Load the source image BEFORE counting toward the ceiling: asking to edit an image that does not
        # exist draws nothing, so there is no reason to spend the user's slot.
        ref_image: RefImage | None = None
        # ONLY ``mode`` has the right to decide, not the presence of imageIndex. The model has a habit of
        # filling every parameter (caught on real Zalo: args {imageIndex: 1} for a request to draw a NEW
        # e-magazine). If imageIndex decided, it would go and edit an old picture in the conversation and
        # the user would get a strange image with nothing saying it is wrong.
        if args.mode == "sua_anh_da_gui":
            wanted_index = args.image_index if args.image_index is not None else 1
            paths = await collect_recent_image_paths(ctx, deps)

            # The conversation has NEVER had an image -> "edit an image" is an impossible intention
            # (nobody asks to edit an image before sending one), so the model surely chose the wrong mode.
            # Drawing new is the only sensible thing. Refusing makes the model flounder rewriting the
            # prompt then give up: that really happened: 5 calls, 68k tokens, the user got nothing.  Very
            # different from the 2 branches below: there the conversation HAS images, so the user really
            # refers to a picture: drawing new would go against what they mean, say the truth.
            if paths:
                rel_path = paths[wanted_index - 1] if wanted_index - 1 < len(paths) else None
                if rel_path is None:
                    return ket_qua_loi(
                        f"Hội thoại chỉ còn {len(paths)} ảnh gần đây - imageIndex {wanted_index} vượt quá. "
                        f'Dùng imageIndex từ 1 đến {len(paths)}, hoặc đổi mode sang "ve_moi".'
                    )
                loaded = await deps.stored_images.load_stored_image(rel_path)
                if loaded is None:
                    return ket_qua_loi(
                        "Ảnh này đã bị dọn khỏi bộ nhớ (quá hạn lưu trữ) nên không đọc được để sửa. "
                        "Nhờ người dùng gửi lại ảnh."
                    )
                ref_image = RefImage(base64=loaded.base64, media_type=loaded.media_type)

        rate = check_image_rate_limit(thread_key)
        if not rate.ok:
            return ket_qua_loi(rate.reason)

        # Only announce once it is certain the drawing will really happen
        await send_notice(TIN_DANG_SUA if ref_image is not None else TIN_DANG_VE)

        try:

            async def bao_thu_lai() -> None:
                # Do NOT charge another slot: ``check_image_rate_limit`` already ran above and the miss
                # just now already spent one. Making the user pay two slots for one image punishes them
                # for the provider's fault.
                await send_notice(TIN_THU_LAI)

            image = await ve_voi_mot_lan_thu_lai(
                generate,
                GenerateImageParams(
                    prompt=args.prompt,
                    ref_image=ref_image,
                    transparent_background=bool(args.transparent_background),
                ),
                bao_thu_lai,
            )
            file_name = f"anh-{int(time.time() * 1000)}.{image.ext}"
            await gui_file_kem_caption(
                ctx, deps, filename=file_name, data=image.data, caption=args.caption, as_image=True
            )
            if ctx.record_sent is not None:
                ctx.record_sent(ghi_chu_da_gui_anh(1, args.caption))
            log.info(
                "Đã gửi ảnh tự vẽ",
                account_id=ctx.account.id,
                thread_id=ctx.message.thread_id,
                kb=round(len(image.data) / 1024),
                sua=ref_image is not None,
            )
            return f"{DELIVERED_NOTE} ({round(len(image.data) / 1024)} KB)"
        except (MediaSendError, Exception) as err:
            reason = str(err)
            log.warning("Vẽ ảnh thất bại", err=err)
            failure: KetQuaLoiTool = ket_qua_loi(
                f"Vẽ ảnh thất bại ({reason}). Nói thật với người dùng, đừng hứa gửi ảnh sau."
            )
            return failure

    return FunctionTool(
        name="create_image",
        description=CREATE_IMAGE_DESCRIPTION,
        input_model=CreateImageInput,
        handler=handler,
    )
