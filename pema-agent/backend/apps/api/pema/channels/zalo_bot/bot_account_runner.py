# ported from: src/zalo-bot/bot-account-runner.ts
"""Start ONE bot account: client -> (webhook registration OR polling loop) -> router -> turn job.

Returns the stop function and the channel. Callable for many accounts; each one has its own loop.

Forced deviations:

* The router and the turn: the polling loop (or the webhook route) hands each update to ``BotMessageRouter``,
  which enqueues a ``TurnJob``; ``route_bot_update`` replaces the in-process ``processBatch`` call.
* The client factory is a parameter (``client_factory``) instead of the module-level
  ``tiemClientRunnerChoTest`` swap, so tests pass a fake without patching anything; nothing goes out to the
  real ``bot-api.zaloplatforms.com``.
* Registers and unregisters the channel in the ``InMemoryChannelRegistry`` (``register`` on start,
  ``unregister`` on stop): the scheduler only holds an ``account_id`` and needs to get this very object back,
  which is the reason the original returned ``kenh``.
* Webhook mode (new): with ``webhook`` given, the account registers ``setWebhook(url, secret)`` instead of
  polling. The two are mutually exclusive on the Bot API.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.zalo_bot.bot_message_router import BotMessageRouter
from pema.channels.zalo_bot.kenh_bot import ZaloBotChannel
from pema.channels.zalo_bot.zalo_bot_api_client import BotApiClient, LoiZaloBotApi, tao_zalo_bot_client
from pema.channels.zalo_bot.zalo_bot_api_types import ZaloBotUpdate
from pema.channels.zalo_bot.zalo_bot_listener import PollHandle, bat_dau_vong_poll
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.logger import create_logger

_log = create_logger("bot-account-runner")


def _default_client(token: str) -> BotApiClient:
    return tao_zalo_bot_client(token)


ClientFactory = Callable[[str], BotApiClient]


@dataclass(frozen=True)
class WebhookRegistration:
    url: str
    secret: str


@dataclass
class RunningBotAccount:
    clinic_id: UUID
    account_id: str
    kenh: ZaloBotChannel
    client: BotApiClient
    poll: PollHandle | None
    registry: InMemoryChannelRegistry

    async def dung(self) -> None:
        if self.poll is not None:
            self.poll.dung()
        self.registry.unregister(self.clinic_id, self.account_id)
        await self.client.aclose()


def _is_token_error(err: LoiZaloBotApi) -> bool:
    # Must read BOTH directions. The first version only had ``err.http_status ?? int(err.ma_loi)`` and the
    # ``??`` branch was DEAD CODE: ``_goi`` always sets ``http_status = res.status`` and Zalo returns the
    # error in the BODY with HTTP **200**. So ``http_status`` was always 200, ``is_token_error`` always False,
    # and the whole fail-fast gate was off: exactly the case of an operator revoking the token (MANDATORY if
    # it leaks) left the dashboard green "Running" while the bot stayed silent forever.
    codes: set[int] = set()
    if err.http_status is not None:
        codes.add(err.http_status)
    with contextlib.suppress(TypeError, ValueError):
        codes.add(int(err.ma_loi))  # pyright: ignore[reportArgumentType]
    return bool(codes & {401, 403})


async def chay_tai_khoan_bot(
    *,
    clinic_id: UUID,
    account_id: str,
    token: str,
    router: BotMessageRouter,
    registry: InMemoryChannelRegistry,
    webhook: WebhookRegistration | None = None,
    client_factory: ClientFactory | None = None,
) -> RunningBotAccount:
    client = (client_factory or _default_client)(token)

    # Check the token BEFORE opening the loop: a wrong token that keeps polling is one error line plus a
    # backoff per round, and the operator only sees "the bot does not answer" without the cause. Token error:
    # stop for good (no amount of waiting fixes it, someone must enter it again). Network error: open the loop
    # anyway, which has its own backoff and heals by itself.
    #
    # Not telling the two apart means one network blink at boot (the container comes up before DNS is ready)
    # kills the bot account FOREVER: ``start_all`` only logs and skips, nobody schedules a retry, and the
    # dashboard shows only "Token stored, not running". Fail-fast here turns a SELF-HEALING state into an
    # incident that needs a person.
    try:
        me = await client.get_me()
        _log.info("Token bot hợp lệ", account_id=account_id, bot=me.get("display_name") or me.get("id"))
    except LoiZaloBotApi as err:
        if _is_token_error(err):
            await client.aclose()
            raise
        _log.warning(
            "Không kiểm được token lúc khởi động (nghi lỗi mạng) - vẫn mở vòng poll, backoff sẽ tự thử lại",
            err=err,
            account_id=account_id,
        )

    kenh = ZaloBotChannel(client, account_id, webhook_secret=None if webhook is None else webhook.secret)

    poll: PollHandle | None = None
    if webhook is not None:
        # Webhook mode: register the URL and the secret, and do NOT poll (the two are mutually exclusive).
        try:
            await client.set_webhook(webhook.url, webhook.secret)
        except LoiZaloBotApi as err:
            await client.aclose()
            raise LoiZaloBotApi(
                f"Không đăng ký được webhook: {err}", "setWebhook", err.http_status, err.ma_loi
            ) from None
    else:
        await _remove_stray_webhook(client, account_id)

        async def on_update(_: str, update: ZaloBotUpdate) -> None:
            await router.route_bot_update(clinic_id, account_id, kenh, update)

        poll = bat_dau_vong_poll(
            account_id=account_id,
            client=client,
            # A FUNCTION, not a number: an edit on the Settings page takes effect at the next round.
            timeout_giay=lambda: get_tuning_int("ZALO_BOT_POLL_TIMEOUT_SECONDS"),
            on_update=on_update,
        )

    # The registry gets the channel so the scheduler (which holds only an ``account_id``, with no incoming
    # message to take a send path from) can find THIS object. The first version of the original returned only
    # ``{ dung }`` and that was the one technical reason scheduled jobs could not run on the bot channel, not
    # that the Bot API lacks proactive sending (measured: 10 messages in 416 ms).
    registry.register(clinic_id, kenh)
    _log.info("Đã khởi động tài khoản bot", account_id=account_id, mode="webhook" if webhook else "polling")
    return RunningBotAccount(clinic_id, account_id, kenh, client, poll, registry)


async def _remove_stray_webhook(client: BotApiClient, account_id: str) -> None:
    # Webhook and getUpdates are MUTUALLY EXCLUSIVE (Zalo says so). With a webhook still on, polling never
    # receives anything, and the symptom is SILENCE, not an error: nearly impossible to guess without checking
    # here.
    webhook_url: str | None = None
    try:
        info = await client.get_webhook_info()
        webhook_url = str(info.get("url") or "") or None
    except LoiZaloBotApi as err:
        # Carry on if it cannot be read: blocking boot here would lose the other accounts over a side call.
        # But WARN, not debug: ``getWebhookInfo`` may not exist on the live API (13 of 17 methods answered 404
        # when measured), in which case the whole detection is dead code, while the symptom of a webhook left
        # on is exactly the "silent forever" it exists to catch.
        _log.warning(
            "Không xác minh được webhook - nếu bot im lặng thì kiểm thủ công "
            "(webhook và long polling loại trừ nhau)",
            err=err,
            account_id=account_id,
        )
    if webhook_url:
        # Separate from the except above: a FAILED removal is exactly the case this block exists to avoid
        # (webhook left on = polling silent forever), so it must WARN and not blend into a debug line "could
        # not read".
        _log.warning(
            "Tài khoản bot đang bật webhook - long polling sẽ KHÔNG nhận được tin. Đang gỡ",
            account_id=account_id,
        )
        try:
            await client.delete_webhook()
        except LoiZaloBotApi as err:
            _log.warning(
                "GỠ WEBHOOK THẤT BẠI - vòng poll sẽ im lặng, không nhận được tin nào",
                err=err,
                account_id=account_id,
            )
