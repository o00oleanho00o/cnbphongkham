# ported from: src/images/image-generation-client.ts
"""Gọi endpoint OpenAI-compatible ``/v1/images/generations`` để vẽ hoặc SỬA ảnh.

Ba quyết định đến từ đo thật trên 9Router (cx/gpt-5.5-image), không phải suy đoán:

1. XIN SSE bằng header ``Accept: text/event-stream``, KHÔNG dùng
   ``?response_format=binary``. Binary nhẹ hơn thật (157KB so với 2.4MB base64)
   nhưng nó chỉ trả byte đầu tiên LÚC VẼ XONG, mà router nằm sau Cloudflare -
   vẽ lâu là ăn HTTP 524 "origin timeout". Đo cùng prompt chạy song song:
   binary byte đầu sau 125.4s -> 524; SSE byte đầu sau 1.8s -> 200 ở giây 62.7.
   Đổi lại tốn ~2.5 lần băng thông (base64 + event tiến độ) - đáng, vì đường
   kia có lúc không ra được ảnh nào.
2. KHÔNG gửi ``size``. Model bỏ qua tham số này: xin 1024x1024 hai lần nhận về
   1024x1536 rồi 1536x1024. Muốn dọc/ngang phải nói trong prompt.
3. Ảnh gốc nằm ở trường ``image`` (không phải ``ref_image``), dạng data URI. Sai
   tên trường thì provider bỏ qua âm thầm - vẫn ra ảnh nhưng là ảnh vẽ mới.

Vẫn đọc được JSON thường và bytes thô: chỉ provider codex mới stream, endpoint
khác nhận header Accept rồi trả JSON như cũ.

``client`` tiêm được để test không chạm mạng (``httpx.MockTransport``) - cùng nếp với SidecarCaller.

Forced deviations: ``fetch`` + ``AbortSignal.timeout`` become an injectable ``httpx.AsyncClient`` (opened with
``stream=True``) inside ``asyncio.timeout``, which like the original signal covers the whole call INCLUDING
the stream read (httpx's own timeouts are per operation, so a client created here gets ``timeout=None`` and
leaves the ceiling to ``IMAGE_GEN_TIMEOUT_MS``); ``Buffer`` becomes ``bytes``; the abort/timeout error
names become ``TimeoutError`` / ``httpx.TimeoutException``; the plain ``Error`` is ``ImageGenError``.
Image generation is switched off in the ``patient_channel`` profile by the policy layer; nothing is
removed here.
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Literal, cast

import httpx

from pema.config.runtime_image_settings import ImageGenSettings, get_image_settings, is_image_gen_configured
from pema.config.runtime_tuning_settings import get_tuning, get_tuning_int
from pema.images.image_retry_policy import ImageGenError, LoiVeHutAnh
from pema.images.read_image_sse_stream import read_image_from_sse_stream, round_half_up

ImageExt = Literal["jpg", "png", "webp"]


@dataclass(frozen=True)
class RefImage:
    base64: str
    media_type: str


@dataclass(frozen=True)
class GenerateImageParams:
    prompt: str
    ref_image: RefImage | None = None
    """Ảnh gốc để sửa, lấy từ media-store (loadStoredImage)"""
    transparent_background: bool = False
    """Cần nền trong suốt (logo, sticker) - ép sang PNG vì JPEG không có alpha"""


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    ext: ImageExt


EXT_BY_MIME: dict[str, ImageExt] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _b64_to_bytes(value: str) -> bytes:
    """``Buffer.from(value, "base64")`` is lenient about missing padding; so is this."""
    stripped = "".join(value.split())
    return base64.b64decode(stripped + "=" * (-len(stripped) % 4))


async def read_error_message(response: httpx.Response) -> str:
    """Lấy câu lỗi từ body. Router trả HAI dạng khác nhau tùy mã lỗi (đo thật):
      400 -> {"error":{"message":"..."}}   error là OBJECT
      401 -> {"error":"API key required"}  error là CHUỖI
    Chỉ đọc ``error.message`` thì sai key sẽ hiện "undefined" cho người dùng.
    """
    try:
        await response.aread()
        raw = response.text
    except Exception:
        raw = ""
    try:
        parsed: object = json.loads(raw)
        if isinstance(parsed, dict):
            err = cast("dict[str, object]", parsed).get("error")
            if isinstance(err, str) and err:
                return err
            if isinstance(err, dict):
                message = cast("dict[str, object]", err).get("message")
                if isinstance(message, str) and message:
                    return message
    except ValueError:
        # Không phải JSON (HTML của proxy, body rỗng) - rơi xuống dùng mã HTTP
        pass
    return f"HTTP {response.status_code}{': ' + raw[:200] if raw else ''}"


async def generate_image(
    params: GenerateImageParams,
    settings: ImageGenSettings | None = None,
    client: httpx.AsyncClient | None = None,
) -> GeneratedImage:
    resolved = settings if settings is not None else get_image_settings()
    if not is_image_gen_configured(resolved):
        raise ImageGenError("Tool vẽ ảnh chưa cấu hình đủ base URL + model + API key")

    # Nền trong suốt bắt buộc PNG - JPEG không có kênh alpha nên nền sẽ ra đen
    output_format = "png" if params.transparent_background else "jpeg"

    body: dict[str, object] = {
        "model": resolved.model,
        "prompt": params.prompt,
        "n": 1,
        "output_format": output_format,
        # Không gửi thì nhà cung cấp tự chọn mức thấp hơn. Đo A/B cùng prompt:
        # "high" ra ảnh giàu chi tiết hơn hẳn mà không chậm hơn.
        "quality": get_tuning("IMAGE_GEN_QUALITY"),
    }
    if params.transparent_background:
        body["background"] = "transparent"
    if params.ref_image is not None:
        body["image"] = f"data:{params.ref_image.media_type};base64,{params.ref_image.base64}"
        # Đọc kỹ ảnh gốc thì mới giữ đúng chi tiết khi sửa
        body["image_detail"] = "high"

    url = f"{resolved.base_url.rstrip('/')}/v1/images/generations"
    # Đuôi file theo format đã XIN: stream SSE và JSON chỉ mang base64 trần, không
    # kèm MIME. Riêng nhánh bytes thô thì Content-Type thật mới là nguồn đúng.
    requested_ext: ImageExt = "png" if output_format == "png" else "jpg"

    timeout_ms = get_tuning_int("IMAGE_GEN_TIMEOUT_MS")
    owns_client = client is None
    # Trần tổng do asyncio.timeout bên dưới giữ; timeout từng thao tác của httpx không phủ được cả stream
    http = httpx.AsyncClient(timeout=None) if client is None else client  # noqa: S113

    try:
        # Trần tổng này phủ CẢ phần đọc stream chứ không riêng lúc mở kết nối: thiếu nó thì
        # provider treo là treo luôn cả lượt agent, người dùng đợi vô hạn.
        async with asyncio.timeout(timeout_ms / 1000):
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {resolved.api_key}",
                # Header quyết định: router chỉ stream khi thấy dòng này. Không có nó
                # thì kết nối im lặng tới lúc vẽ xong và Cloudflare cắt bằng 524.
                "Accept": "text/event-stream",
            }
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            async with http.stream("POST", url, headers=headers, content=payload) as response:
                if not response.is_success:
                    raise ImageGenError(await read_error_message(response))
                return await read_image_response(response, requested_ext)
    except (TimeoutError, httpx.TimeoutException) as exc:
        # Bọc CẢ lượt gọi lẫn lượt đọc stream: với SSE, lời gọi trả về sau vài giây
        # rồi mình còn đọc thêm cả phút - quá hạn giữa chừng là ca dễ xảy ra nhất,
        # mà bọc mỗi lời gọi thì nó lọt ra ngoài dạng lỗi timeout trần trụi.
        raise ImageGenError(
            f"Vẽ ảnh quá lâu (hơn {round_half_up(timeout_ms / 1000)} giây) nên đã dừng"
        ) from exc
    finally:
        if owns_client:
            await http.aclose()


async def read_image_response(response: httpx.Response, requested_ext: ImageExt) -> GeneratedImage:
    """Đọc ảnh ra khỏi response, chịu được cả 3 kiểu provider có thể trả về"""
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()

    if content_type == "text/event-stream":
        return GeneratedImage(
            data=_b64_to_bytes(await read_image_from_sse_stream(response)), ext=requested_ext
        )

    if content_type == "application/json":
        b64: str | None = None
        try:
            await response.aread()
            parsed: object = json.loads(response.text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            items = cast("dict[str, object]", parsed).get("data")
            if isinstance(items, list) and items and isinstance(cast("list[object]", items)[0], dict):
                value = cast("dict[str, object]", cast("list[object]", items)[0]).get("b64_json")
                b64 = value if isinstance(value, str) else None
        # Cùng lớp với nhánh SSE: chạy xong mà không ra ảnh -> đáng thử lại. Nhánh
        # Content-Type lạ bên dưới thì KHÔNG: đó là trang lỗi hạ tầng, không phải
        # model đổi ý.
        if not b64:
            raise LoiVeHutAnh("Provider không trả về ảnh (JSON thiếu b64_json)")
        return GeneratedImage(data=_b64_to_bytes(b64), ext=requested_ext)

    ext = EXT_BY_MIME.get(content_type)
    if ext is None:
        # Trang lỗi HTML của proxy chẳng hạn - đừng ghi ra file .jpg rồi gửi cho
        # người dùng một file hỏng
        raise ImageGenError(f"Provider không trả về ảnh (Content-Type: {content_type or 'trống'})")
    return GeneratedImage(data=await response.aread(), ext=ext)
