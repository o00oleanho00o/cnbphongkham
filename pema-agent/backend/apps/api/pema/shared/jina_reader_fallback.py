# ported from: src/shared/jina-reader-fallback.ts
"""Lưới đỡ khi tự fetch không lấy được nội dung: đẩy URL qua Jina Reader (r.jina.ai) - dịch vụ render trang
rồi trả markdown sạch.

Vì sao cần (đo thực tế trên đúng các trang bot đã thất bại):
- giavang.doji.vn: tự fetch ECONNRESET, qua Jina ra nội dung (trang render JS)
- vnexpress.net: tự fetch 406, qua Jina ra 40k ký tự
Đây đúng pattern của GoClaw (ExtractorChain: Defuddle hosted trước, bóc in-process sau) và Hermes (Firecrawl
gateway trước, provider khác sau).

Đánh đổi phải biết:
- Chậm: đo được 1,2s tới 15,8s (tự fetch tính bằng trăm ms)
- URL bị gửi qua bên thứ ba -> tắt được bằng WEB_FETCH_FALLBACK_ENABLED
- Không key thì có rate limit; site sau Cloudflare vẫn chặn (Jina trả nguyên văn
  "Warning: Target URL returned error 403")

Module thuần, không import env - caller truyền cấu hình vào.

Clinic note: this module sends the page URL to a third party. In the ``patient_channel`` policy profile the
web tools are switched off by the policy layer, so nothing calls it there; the feature itself is kept.

Forced deviations from the TypeScript original:

* ``fetchFn?: typeof fetch`` -> ``client: httpx.AsyncClient | None`` (tests pass a client over
  ``httpx.MockTransport``). Without one, a client is created for the call.
* ``AbortSignal.any([timeout, signal])`` -> ``asyncio.timeout`` around the call plus ``run_abortable`` with
  the turn's ``AbortSignal`` (``pema.shared.safe_remote_download``): whichever fires first cancels the
  request.
* ``timeoutMs`` / ``maxChars`` / ``apiKey`` keep their meaning as ``timeout_ms`` / ``max_chars`` /
  ``api_key``.
* The log fields carry the HOST of the URL, not the URL: a query string can hold identifiers or signed
  tokens.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from pema.shared.logger import create_logger
from pema.shared.safe_remote_download import AbortSignal, run_abortable

log = create_logger("jina-reader")
ENDPOINT = "https://r.jina.ai/"
TIMEOUT_MS = 45_000

UPSTREAM_BLOCKED = re.compile(r"^Warning: Target URL returned error [0-9]+", re.MULTILINE)
"""Jina trả 200 kèm dòng cảnh báo này khi trang đích vẫn chặn nó."""

_TITLE_LINE = re.compile(r"^Title:\s*(.+)$", re.MULTILINE)
_MARKER = "Markdown Content:"


@dataclass(frozen=True)
class JinaFetchOptions:
    max_chars: int
    api_key: str | None = None
    """Key tuỳ chọn - có key thì hạn mức cao hơn, không có vẫn chạy."""
    timeout_ms: int | None = None
    client: httpx.AsyncClient | None = None
    signal: AbortSignal | None = None
    """Signal của lượt (hết ``LLM_TURN_TIMEOUT_MS`` hoặc bị hủy) - gộp với timeout riêng."""


@dataclass(frozen=True)
class JinaResult:
    text: str
    title: str


def parse_jina_response(body: str) -> JinaResult:
    """Jina trả "Title: ...\\nURL Source: ...\\n\\nMarkdown Content:\\n<nội dung>"."""
    title_match = _TITLE_LINE.search(body)
    title = title_match.group(1).strip() if title_match else ""
    marker = body.find(_MARKER)
    text = body[marker + len(_MARKER) :].strip() if marker >= 0 else body.strip()
    return JinaResult(text=text, title=title)


def _host_of(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


async def fetch_via_jina_reader(url: str, options: JinaFetchOptions) -> JinaResult | None:
    """Trả None (không throw) khi hỏng - caller đang ở nhánh lưới đỡ, hỏng thêm lần nữa thì chỉ việc báo thật
    cho model."""
    timeout_s = (options.timeout_ms if options.timeout_ms is not None else TIMEOUT_MS) / 1000
    host = _host_of(url)
    headers = {"Accept": "text/plain"}
    if options.api_key:
        headers["Authorization"] = f"Bearer {options.api_key}"

    async def get() -> httpx.Response:
        if options.client is not None:
            return await options.client.get(f"{ENDPOINT}{url}", headers=headers, follow_redirects=True)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            return await client.get(f"{ENDPOINT}{url}", headers=headers)

    try:
        # Gộp timeout riêng của Jina với signal của lượt: cái nào bắn trước thì hủy.
        async with asyncio.timeout(timeout_s):
            res = await run_abortable(get(), options.signal)
        if not res.is_success:
            log.debug("Jina Reader trả lỗi", host=host, status=res.status_code)
            return None

        body = res.text
        # Jina trả HTTP 200 kể cả khi trang đích chặn NÓ - phải tự soi dòng cảnh báo
        if UPSTREAM_BLOCKED.search(body):
            log.debug("Trang đích chặn cả Jina Reader", host=host)
            return None

        parsed = parse_jina_response(body)
        if not parsed.text:
            return None
        text = parsed.text[: options.max_chars] if len(parsed.text) > options.max_chars else parsed.text
        return JinaResult(title=parsed.title, text=text)
    except Exception as err:
        log.debug("Gọi Jina Reader thất bại", host=host, err=err)
        return None
