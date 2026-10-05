# ported from: src/agent/tools/web-fetch-tool.ts
"""Đọc nội dung 1 URL cho agent theo chuỗi 2 tầng (pattern ExtractorChain của GoClaw): tự fetch trước cho
nhanh và riêng tư, hỏng hoặc ra quá ít chữ thì đẩy qua Jina Reader - dịch vụ này render được trang JavaScript
và qua được một phần chặn bot.

Tầng tự fetch đi qua ``safe_remote_download`` nên thừa hưởng toàn bộ guard SSRF. Tầng Jina gửi URL ra bên thứ
ba, tắt được bằng WEB_FETCH_FALLBACK_ENABLED.

Forced deviations:

* ``tool({...})`` of the Vercel AI SDK -> ``FunctionTool``; zod ``z.string().url()`` -> a pydantic validator
  built on ``parse_public_url`` (any scheme that parses, like ``new URL``; http/https is enforced later by the
  guard) with ``format: uri`` kept in the JSON schema.
* ``execute({url}, {abortSignal})``: the AI SDK handed the per-call ``abortSignal`` to ``execute``;
  ``FunctionTool.execute`` has no such argument, so the signal is a factory parameter (``abort_signal``,
  default ``None``). Task cancellation of the turn also reaches the awaits below. Open item for D1/the
  registry: pass the turn's ``AbortSignal`` here when it builds the tool.
* The downloader, the Jina fallback and the transports are keyword-only injection points so the tests need no
  network (the original used a loopback URL and replaced ``globalThis.fetch``).
* Logs carry the HOST of the URL, never the URL: a query string can hold identifiers or signed tokens.

Clinic note: the Jina tier sends the URL to a third party. The registry switches this tool off in the
``patient_channel`` policy profile; the feature itself is kept.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.tag_ky_tu_an import loc_ky_tu_an
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.agent.tools.wrap_untrusted_content import wrap_untrusted_content
from pema.config.runtime_tool_settings import get_fetch_settings
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.html_to_text import extract_html_title, html_to_readable_text
from pema.shared.jina_reader_fallback import JinaFetchOptions, JinaResult, fetch_via_jina_reader
from pema.shared.logger import create_logger
from pema.shared.safe_remote_download import (
    AbortSignal,
    DownloadOptions,
    HostResolver,
    RemoteFile,
    download_from_public_url,
    parse_public_url,
)

type DownloadFn = Callable[[str, DownloadOptions], Awaitable[RemoteFile]]
type JinaFn = Callable[[str, JinaFetchOptions], Awaitable[JinaResult | None]]

# HTML 3MB là quá đủ cho trang tin/bài viết; cap TRƯỚC khi parse để trang khổng lồ không ăn RAM. Text trả cho
# model cap riêng (WEB_FETCH_MAX_CHARS) để không phình context.
MAX_HTML_BYTES = 3 * 1024 * 1024

# Dưới ngưỡng này coi như "fetch được nhưng rỗng" - trang render bằng JavaScript hay ra vài chục ký tự khung
# sườn. Đáng để thử lại qua Jina.
TOO_LITTLE_TEXT = 200

log = create_logger("web-fetch")

DESCRIPTION = (
    "Đọc nội dung văn bản của 1 trang web theo URL (http/https công khai). Dùng sau web_search để đọc chi "
    "tiết, hoặc khi người dùng gửi link. Trang cần đăng nhập thì không đọc được."
)


@dataclass(frozen=True)
class FetchedPage:
    text: str
    title: str
    via: Literal["truc-tiep", "jina-reader"]


class WebFetchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        description="URL đầy đủ, vd https://example.com/bai-viet", json_schema_extra={"format": "uri"}
    )

    @field_validator("url")
    @classmethod
    def _must_be_a_url(cls, value: str) -> str:
        try:
            parse_public_url(value)
        except Exception:
            raise ValueError("Invalid url") from None
        return value


def _host_of(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def create_web_fetch_tool(
    *,
    download: DownloadFn | None = None,
    jina: JinaFn = fetch_via_jina_reader,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: HostResolver | None = None,
    jina_client: httpx.AsyncClient | None = None,
    abort_signal: AbortSignal | None = None,
) -> FunctionTool[WebFetchInput]:
    async def default_download(url: str, options: DownloadOptions) -> RemoteFile:
        return await download_from_public_url(url, options, transport=transport, resolver=resolver)

    download_fn: DownloadFn = download if download is not None else default_download

    async def fetch_direct(url: str) -> FetchedPage | None:
        """Tự fetch: nhanh, riêng tư, miễn phí. Hỏng thì trả None để rơi xuống lưới đỡ."""
        try:
            file = await download_fn(url, DownloadOptions(max_bytes=MAX_HTML_BYTES, signal=abort_signal))
            is_html = "html" in file.media_type or file.media_type == "application/octet-stream"
            raw = file.data.decode("utf-8", errors="replace")
            text = html_to_readable_text(raw) if is_html else raw.strip()
            if len(text) < TOO_LITTLE_TEXT:
                log.debug("Fetch trực tiếp ra quá ít chữ", host=_host_of(url), length=len(text))
                return None
            return FetchedPage(text=text, title=extract_html_title(raw) if is_html else "", via="truc-tiep")
        except Exception as err:
            log.debug("Fetch trực tiếp thất bại", host=_host_of(url), err=err)
            return None

    async def handler(args: WebFetchInput) -> object:
        url = args.url
        max_chars = get_tuning_int("WEB_FETCH_MAX_CHARS")

        # ``abort_signal`` bắn khi lượt hết ``LLM_TURN_TIMEOUT_MS`` hoặc bị hủy. Forward xuống tận socket để
        # URL người lạ treo/nhỏ giọt không tải nền sau khi lượt đã bỏ cuộc.
        page = await fetch_direct(url)
        if page is None and get_fetch_settings().fallback_enabled:
            found = await jina(
                url, JinaFetchOptions(max_chars=max_chars, client=jina_client, signal=abort_signal)
            )
            if found is not None:
                page = FetchedPage(text=found.text, title=found.title, via="jina-reader")

        if page is None:
            return ket_qua_loi(
                f"Không đọc được trang {url}. "
                "Trang có thể chặn bot hoặc yêu cầu đăng nhập - thử một nguồn khác."
            )

        log.info("Đã đọc trang web", host=_host_of(url), via=page.via, length=len(page.text))

        truncated = len(page.text) > max_chars
        body = f"{page.text[:max_chars]}\n[...đã cắt bớt, trang còn dài]" if truncated else page.text

        # Lọc dải Tags (ASCII smuggling, xem ``tag_ky_tu_an``) TRƯỚC khi bọc - trang web là nguồn KHÔNG kiểm
        # soát y hệt tài liệu KB, nghiên cứu yêu cầu lọc ở CẢ HAI tầng nạp.
        return wrap_untrusted_content(loc_ky_tu_an(body), f"{url}{f' - {page.title}' if page.title else ''}")

    return FunctionTool(name="web_fetch", description=DESCRIPTION, input_model=WebFetchInput, handler=handler)
