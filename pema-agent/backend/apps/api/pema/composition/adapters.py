"""Small adapters between the Protocols of one package and the real objects of another (package G).

Every package coded against a Protocol of its own (``ToolDeps``, ``RouterDeps``, ``OutboundPipeline``, ...);
these classes are the glue that the composition root installs. They contain no business rule: each one only
renames, converts a dataclass or routes a call. A rule that belongs to a package stays in that package.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from pema.agent.tools.tool_deps import (
    CleanedReply,
    ParseScheduleResult,
    StoredImage,
    StyledText,
)
from pema.agent.vision_sidecar import SidecarImage, ask_about_image
from pema.channels.markdown_to_zalo_styles import markdown_sang_style_zalo
from pema.channels.prepare_outgoing_text import dinh_dang_neu_bat, lam_sach_theo_cau_hinh
from pema.channels.sanitize_reply_text import lam_sach_giu_dinh_dang, lam_sach_tra_loi
from pema.channels.send_reply_in_parts import reply_target_from_channel, send_reply_in_parts
from pema.channels.zalo_bot.nang_luc_kenh_bot import ZALO_BOT_CAPABILITIES
from pema.channels.zalo_personal.bridge_client import ZaloApi, ZaloBridgeError
from pema.channels.zalo_personal.kenh_ca_nhan import ZaloPersonalChannel
from pema.channels.zalo_personal.zalo_image_variant import estimate_image_tokens, read_image_size
from pema.config.runtime_settings_store import RuntimeSettingsSnapshot, get_runtime_settings
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.conversation.media_store import (
    DownloadedImage,
    MediaStore,
    PersistableImage,
    PersistableMessage,
)
from pema.middleware.rate_limiter import enqueue_send
from pema.scheduler.ports import (
    ReplyResult as SchedulerReplyResult,
)
from pema.scheduler.ports import (
    ReplyTarget as SchedulerReplyTarget,
)
from pema.scheduler.ports import SanitizedText
from pema.scheduler.schedule_parser import ParseScheduleError, ParseScheduleParams, parse_schedule
from pema.shared.download_image import download_image
from pema.shared.logger import create_logger
from pema.video.gui_video_qua_zalo import ZaloVideoApi
from pema_contracts.channel import (
    ChannelCapabilities,
    ChannelKind,
    ChannelPort,
    InboundMessage,
    TextStyle,
    ThreadKind,
)
from pema_contracts.installation import installation_clinic_id, installation_clinic_id_or_none
from pema_contracts.knowledge import KnowledgeStore
from pema_contracts.scheduler import ScheduleInput
from pema_contracts.tools import ToolContext

log = create_logger("composition")


# ------------------------------------------------------------------------------------------ sending


class RateLimitedSendQueue:
    """``SendQueue`` of ``ToolDeps``: ``enqueue_send`` of the rate limiter (C1), awaited."""

    async def enqueue_send[T](self, thread_key: str, send: Callable[[], Awaitable[T]]) -> T:
        return await enqueue_send(thread_key, send)


class ReplyCleaner:
    """``ReplyTextCleaner`` of ``ToolDeps`` over ``sanitize_reply_text`` (C2)."""

    def clean_reply(self, text: str) -> CleanedReply:
        result = lam_sach_tra_loi(text)
        return CleanedReply(text=result.text, blocked=result.chan)

    def clean_keep_formatting(self, text: str) -> CleanedReply:
        result = lam_sach_giu_dinh_dang(text)
        return CleanedReply(text=result.text, blocked=result.chan)


class MarkdownStyler:
    """``MarkdownStyler`` of ``ToolDeps`` over ``markdown_to_zalo_styles`` (C2)."""

    def markdown_to_styles(self, text: str) -> StyledText:
        result = markdown_sang_style_zalo(text)
        return StyledText(text=result.text, styles=list(result.styles))


class SchedulerOutboundPipeline:
    """``OutboundPipeline`` of the scheduler over the shared outbound pipeline of C2."""

    def sanitize_for_config(self, text: str) -> SanitizedText:
        result = lam_sach_theo_cau_hinh(text)
        return SanitizedText(text=result.text, chan=result.chan, da_sua=tuple(result.da_sua))

    def format_if_enabled(self, text: str) -> tuple[str, list[TextStyle]]:
        result = dinh_dang_neu_bat(text)
        return result.text, list(result.styles)

    async def send_reply_in_parts(
        self, target: SchedulerReplyTarget, text: str, styles: Sequence[TextStyle] = ()
    ) -> SchedulerReplyResult:
        # ``proactive=True``: the channel then applies its proactive guard (kill switch, window, cap).
        reply_target = reply_target_from_channel(
            target.channel, target.thread_id, target.thread_kind, target.thread_key, proactive=True
        )
        sent = await send_reply_in_parts(reply_target, text, styles)
        return SchedulerReplyResult(
            sent_parts=sent.sent_parts, delivered_text=sent.delivered_text, error=sent.error
        )


# ------------------------------------------------------------------------------------ runtime settings


class SnapshotRuntimeSettingsKv:
    """``RuntimeSettingsKv`` (D4 settings readers) over the ``RuntimeSettingsSnapshot`` (D1) of the
    installation clinic.

    The synchronous ``get`` reads the snapshot (empty until its first refresh, so the environment and the
    defaults apply). A write goes to the installation clinic and is refused while its id is not loaded."""

    def __init__(self, snapshot: RuntimeSettingsSnapshot | None = None) -> None:
        self._snapshot = snapshot

    def _current(self) -> RuntimeSettingsSnapshot:
        return self._snapshot if self._snapshot is not None else get_runtime_settings()

    def get(self, key: str) -> str | None:
        return self._current().read(key)

    async def aset(self, key: str, value: str) -> None:
        await self._current().set(installation_clinic_id(), key, value)

    async def adelete(self, key: str) -> None:
        await self._current().delete(installation_clinic_id(), key)


# ------------------------------------------------------------------------------------------ images


class MediaImages:
    """Images on the media volume for the three consumers that name them differently.

    * the engine reads a stored image SYNCHRONOUSLY and with no clinic argument (``StoredImageLoader`` of
      ``history_to_model_messages``): the clinic is the installation clinic;
    * the tools read it asynchronously (``StoredImageLoader`` of ``ToolDeps``) with the same rule;
    * the channel pipeline persists the images of ``InboundMessage`` s.
    """

    def __init__(self, media: MediaStore) -> None:
        self._media = media

    def load_sync(self, rel_path: str) -> Any:
        clinic_id = installation_clinic_id_or_none()
        if clinic_id is None:
            return None
        return self._media.load_stored_image_sync(clinic_id, rel_path)

    async def load_stored_image(self, rel_path: str) -> StoredImage | None:
        clinic_id = installation_clinic_id_or_none()
        if clinic_id is None:
            return None
        image = await self._media.load_stored_image(clinic_id, rel_path)
        return None if image is None else StoredImage(base64=image.base64, media_type=image.media_type)

    async def persist(self, clinic_id: UUID, account_id: str, messages: Sequence[InboundMessage]) -> None:
        """``ImagePersister`` of the channel pipeline: downloads, stamps ``local_path`` on each image."""
        items = [
            PersistableMessage(
                thread_id=m.thread_id,
                msg_id=m.msg_id,
                images=[PersistableImage(url=i.url, local_path=i.local_path) for i in m.images],
            )
            for m in messages
        ]
        await self._media.persist_batch_images(clinic_id, account_id, items)
        for message, persisted in zip(messages, items, strict=True):
            for image, saved in zip(message.images, persisted.images, strict=True):
                image.local_path = saved.local_path


async def download_for_media_store(url: str) -> DownloadedImage | None:
    """``ImageDownloader`` of the media store over the SSRF-guarded ``download_image`` (D4)."""
    downloaded = await download_image(url)
    return None if downloaded is None else DownloadedImage(downloaded.data, downloaded.media_type)


def describe_image_bytes(data: bytes) -> Mapping[str, object] | None:
    """What the media store logs about a saved image (size and a token estimate), from the header only."""
    size = read_image_size(data)
    if size is None:
        return None
    return {"width": size[0], "height": size[1], "tokens": estimate_image_tokens(*size)}


class VisionSidecarAdapter:
    """``VisionSidecar`` of ``ToolDeps`` over ``ask_about_image`` (D1)."""

    async def ask_about_image(self, image: StoredImage, question: str) -> str:
        return await ask_about_image(SidecarImage(image.base64, image.media_type), question)


# ----------------------------------------------------------------------------------------- scheduler


class ScheduleParserAdapter:
    """``ScheduleParser`` of ``ToolDeps`` over ``parse_schedule`` (S)."""

    def parse_schedule(
        self, schedule: ScheduleInput, *, time_zone: str, min_interval_minutes: int
    ) -> ParseScheduleResult:
        result = parse_schedule(
            schedule, ParseScheduleParams(time_zone=time_zone, min_interval_minutes=min_interval_minutes)
        )
        if isinstance(result, ParseScheduleError):
            return ParseScheduleResult(ok=False, error=result.error)
        return ParseScheduleResult(ok=True, schedule=result.schedule)


# ------------------------------------------------------------------------------------------ knowledge


class KbAvailabilitySnapshot:
    """``KbAvailability`` of ``ToolDeps``: synchronous probes (they run on every turn and on the Tools page)
    over a snapshot that ``refresh`` rebuilds from the store for the installation clinic. It only decides
    whether the tool is OFFERED; ``kb_search`` itself is scoped by agent binding (default-deny), so the
    snapshot can never widen what a turn may read."""

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store
        self._agents_with_sources: set[str] = set()
        self._any_source = False
        self._task: asyncio.Task[None] | None = None

    def agent_has_sources(self, agent_id: str) -> bool:
        return agent_id in self._agents_with_sources

    def any_source(self) -> bool:
        return self._any_source

    async def refresh(self) -> None:
        agents: set[str] = set()
        any_source = False
        clinic_id = installation_clinic_id()
        sources = await self._store.list_sources(clinic_id)
        if sources:
            any_source = True
        for source in sources:
            agents.update(await self._store.agents_of_source(clinic_id, source.id))
        self._agents_with_sources = agents
        self._any_source = any_source

    def start(self, interval_s: float = 30.0) -> None:
        if self._task is not None:
            return

        async def loop() -> None:
            while True:
                try:
                    await self.refresh()
                except Exception as err:
                    log.warning("kb availability refresh failed", err=err)
                await asyncio.sleep(interval_s)

        self._task = asyncio.get_running_loop().create_task(loop())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return


# --------------------------------------------------------------------------------- channels and video


@dataclass(frozen=True)
class StaticChannelCapabilities:
    """``ChannelCapabilitiesProvider`` of the Tools page: what a channel KIND can do, with no running
    account to ask (``capabilities_for``)."""

    def capabilities_for(self, kind: ChannelKind) -> ChannelCapabilities:
        if kind is ChannelKind.ZALO_BOT:
            return ZALO_BOT_CAPABILITIES
        if kind is ChannelKind.ZALO_PERSONAL:
            return ChannelCapabilities(
                channel=ChannelKind.ZALO_PERSONAL,
                can_send_proactive=True,
                max_text_length=get_tuning_int("ZALO_MAX_MESSAGE_CHARS"),
                supports_formatting=True,
                supports_quote=True,
                supports_typing_indicator=True,
                supports_read_receipt=True,
                supports_reactions=True,
                supports_send_image=True,
                supports_send_file=True,
                supports_send_video=True,
                supports_group_info=True,
                supports_tag_member=True,
            )
        return ChannelCapabilities(channel=kind, can_send_proactive=False)


class BridgeVideoApi:
    """``ZaloVideoApi`` over the bridge account API (the upload road of ``tai_video``).

    The bridge cannot hand back the URL of an uploaded attachment, so ``upload_attachment`` refuses: the
    poster step then fails and ``tai_video`` takes its documented fallback, sending the video AS A FILE
    (``send_message`` with an attachment, which the bridge sends through ``send_attachment``). A video card
    with a poster needs the bridge to expose uploads: open item."""

    def __init__(self, api: ZaloApi) -> None:
        self._api = api

    async def upload_attachment(self, items: list[dict[str, Any]], thread_id: str, thread_type: int) -> Any:
        raise ZaloBridgeError("unsupported", "the bridge does not expose attachment uploads")

    async def send_video(self, options: dict[str, Any], thread_id: str, thread_type: int) -> Any:
        return await self._api.send_video(
            thread_id=thread_id,
            thread_type=_kind_of(thread_type),
            video_url=str(options.get("videoUrl", "")),
            caption="",
        )

    async def send_message(self, content: dict[str, Any], thread_id: str, thread_type: int) -> Any:
        attachments: object = content.get("attachments")
        if not isinstance(attachments, list) or not attachments:
            raise ZaloBridgeError("unsupported", "only attachment messages are sent through this road")
        first = cast("dict[str, Any]", attachments[0])  # pyright: ignore[reportUnknownArgumentType]
        data = first.get("data")
        if not isinstance(data, bytes):
            raise ZaloBridgeError("unsupported", "the attachment has no bytes")
        filename = str(first.get("filename", "video.mp4"))
        return await self._api.send_attachment(
            thread_id=thread_id,
            thread_type=_kind_of(thread_type),
            filename=filename,
            data=data,
            caption="",
        )


def _kind_of(thread_type: int) -> ThreadKind:
    return ThreadKind.GROUP if thread_type == 1 else ThreadKind.USER


def video_api_for(ctx: ToolContext) -> ZaloVideoApi | None:
    """``ToolDeps.video_api_for``: the bridge road for a personal account, nothing for the other channels."""
    channel: ChannelPort | None = ctx.channel
    if isinstance(channel, ZaloPersonalChannel):
        return BridgeVideoApi(channel.api)
    return None
