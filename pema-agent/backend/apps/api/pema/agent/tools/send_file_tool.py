# ported from: src/agent/tools/send-file-tool.ts
"""``send_file``: send one file to the current conversation.

Source: a file name that exists in the ``shared-files`` store (e.g. ``bao-gia.pdf``) or a public http(s) URL.

Forced deviations:

* the temp file (``withTempFile``) is gone: the file travels as bytes through ``MediaChannel.send_file``
  (see ``send_attachment_with_caption``);
* the AI SDK passed an ``abortSignal`` to ``execute``; the ``AgentTool`` contract has none, so the
  download runs without an external signal (it still has its own timeout and byte cap);
* the data directory is ``Settings.data_dir`` (``PEMA_DATA_DIR``), no longer a global ``dataDir``. Where
  files live in production (object storage vs a local volume) is an open item of CONTRACTS-AI01 section 9.

Policy: switched off in ``patient_channel`` by the registry (it is one of ``MEDIA_AND_WEB_TOOL_KEYS``);
the feature itself is intact for ``staff_assistant``."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.send_attachment_with_caption import MediaSendError, gui_file_kem_caption
from pema.agent.tools.sent_by_tool_note import ghi_chu_da_gui_file
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.config.env import get_settings
from pema.shared.safe_remote_download import (
    DownloadOptions,
    RemoteFile,
    download_from_public_url,
)
from pema_contracts.tools import ToolContext

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
"""Ceiling for downloading a file from a URL: a SELF-IMPOSED POLICY, not a Zalo limit. The real limit sits
in ``settings.features.sharefile.max_size_share_file_v3`` returned by the Zalo server at login and checked
by zca-js (it throws with a concrete number of MB). The number here only avoids downloading hundreds of MB
to find out it is useless."""

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

DESCRIPTION = (
    "Gửi 1 file cho cuộc trò chuyện hiện tại. Nguồn: tên file có sẵn trong kho shared-files "
    "(vd 'bao-gia.pdf') hoặc URL http(s) công khai."
)

type Downloader = Callable[[str, DownloadOptions], Awaitable[RemoteFile]]


class SendFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Tên file trong shared-files hoặc URL http(s)")
    caption: str | None = Field(default=None, description="Chú thích kèm file (tùy chọn)")


def shared_files_dir() -> Path:
    return get_settings().data_dir / "shared-files"


def _base_name(source: str) -> str:
    """``path.basename`` (both separators): blocks path traversal such as ``../../data/accounts/...``."""
    return PurePosixPath(source.replace("\\", "/")).name


def create_send_file_tool(
    ctx: ToolContext,
    deps: ToolDeps,
    download: Downloader = download_from_public_url,
) -> FunctionTool[SendFileInput]:
    async def send_attachment(data: bytes, caption: str | None, display_name: str) -> None:
        # Record history RIGHT INSIDE the send function so the two branches (URL and the shared-files
        # store) cannot forget: this message does not pass ``deliver_chat_reply`` so nobody records it on
        # our behalf.
        await gui_file_kem_caption(ctx, deps, filename=display_name, data=data, caption=caption)
        if ctx.record_sent is not None:
            ctx.record_sent(ghi_chu_da_gui_file(display_name, caption))

    async def handler(args: SendFileInput) -> object:
        # Only allowed: a file in ``data/shared-files`` (blocks the agent reading arbitrary files on the
        # machine, e.g. credentials) or a public http(s) URL.  The URL source is decided by the LLM, and
        # the LLM reads messages from strangers, so the download must go through safe-remote-download:
        # block internal IPs (SSRF: loopback, 169.254.169.254...) and cut the stream past 25MB.
        try:
            if _URL_RE.match(args.source):
                file = await download(args.source, DownloadOptions(max_bytes=MAX_DOWNLOAD_BYTES))
                await send_attachment(file.data, args.caption, file.file_name)
                return "Đã gửi file thành công"

            name = _base_name(args.source)
            file_path = shared_files_dir() / name
            if not name or not file_path.is_file():
                return ket_qua_loi(f'Không có file "{args.source}" trong kho shared-files')
            await send_attachment(file_path.read_bytes(), args.caption, name)
            return "Đã gửi file thành công"
        except MediaSendError as err:
            return ket_qua_loi(f"Gửi file thất bại: {err}")
        except Exception as err:
            return ket_qua_loi(f"Gửi file thất bại: {err}")

    return FunctionTool(name="send_file", description=DESCRIPTION, input_model=SendFileInput, handler=handler)
