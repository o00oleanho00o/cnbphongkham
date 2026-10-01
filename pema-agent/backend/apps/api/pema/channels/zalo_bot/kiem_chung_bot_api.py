# ported from: src/zalo-bot/kiem-chung-bot-api.ts
"""Script that probes the Zalo Bot API with a REAL token. Run: ``python -m
pema.channels.zalo_bot.kiem_chung_bot_api``.

Three questions the public documentation does NOT answer, which this script answers:

1. Can the bot message someone who has not written first (decides the fate of the scheduled-message feature on
  this channel).
2. Does ``getUpdates`` LOSE messages when two arrive close together (it returns ONE update per call and has NO
  ``offset`` to acknowledge a read).
3. The real rate limit.

The script only READS and sends messages to the person who is testing: it touches no DB and no running
account.

Forced deviation (a security improvement): the token comes from the environment variable
``PEMA_ZALO_BOT_PROBE_TOKEN`` (or ``ZALO_BOT_TOKEN``), NOT from ``argv``: a command line argument is visible
to every process list and ends up in shell history. Use a throwaway test bot, never a clinic's production
token. Output goes through ``sys.stdout`` (this is a CLI whose job is to print).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from pema.channels.zalo_bot.zalo_bot_api_client import BotApiClient, LoiZaloBotApi, tao_zalo_bot_client

ENV_NAMES = ("PEMA_ZALO_BOT_PROBE_TOKEN", "ZALO_BOT_TOKEN")


def _out(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def _row(label: str, value: object) -> None:
    _out(f"  {label:<34} {value if isinstance(value, str) else repr(value)}")


async def probe(client: BotApiClient, *, write: Callable[[str], None] = _out) -> int:
    """Run the probe steps. Returns the process exit code."""
    write("\n=== 1. Token sống chưa (getMe) ===")
    _row("bot", await client.get_me())

    write("\n=== 2. Webhook có đang bật không ===")
    # Webhook and getUpdates are MUTUALLY EXCLUSIVE: with a webhook on, polling never receives anything and
    # the symptom is "silence", not an error.
    try:
        wh = await client.get_webhook_info()
        url = wh.get("url")
        _row("webhook", f"ĐANG BẬT: {url} - phải gỡ mới poll được" if url else "không có (tốt)")
    except LoiZaloBotApi as err:
        _row("webhook", f"không đọc được: {err}")

    write("\n=== 3. Nhắn cho tôi một tin từ Zalo, đang chờ 60 giây... ===")
    write("   (mở Zalo, tìm bot vừa tạo, gửi bất kỳ chữ gì)")
    u = await client.get_updates(60)
    if u is None or u.message is None:
        write("   KHÔNG nhận được gì. Kiểm lại: đã nhắn cho ĐÚNG bot chưa, webhook đã gỡ chưa.")
        return 1
    m = u.message
    _row("event_name", u.event_name)
    _row("chat.id", m.chat.id if m.chat else None)
    _row("chat_type", m.chat.chat_type if m.chat else None)
    _row("date (thô)", m.date)
    _row("date (đọc ra)", datetime.fromtimestamp((m.date or 0) / 1000, UTC).isoformat())
    # The sender name and the text are PERSONAL data of the tester: they are deliberately NOT printed.

    chat_id = m.chat.id if m.chat else None
    if not chat_id:
        write("   Thiếu chat.id trong payload - dừng.")
        return 1

    write("\n=== 4. Gửi trả lời + markdown có được server dựng không ===")
    # Pass ``"markdown"`` EXPLICITLY: the client default is now ``None`` (plain text), so omitting it would
    # measure that default and wrongly conclude "parse_mode does NOT work".
    await client.send_message(
        chat_id, "**Đậm** _nghiêng_ - nếu bạn thấy dấu sao thì parse_mode KHÔNG chạy.", "markdown"
    )
    _row("sendMessage", "đã gửi - kiểm bằng MẮT trên Zalo")

    write("\n=== 5. Dấu 'đang nhập' ===")
    try:
        await client.send_chat_action(chat_id)
        _row("sendChatAction", "OK")
    except LoiZaloBotApi as err:
        _row("sendChatAction", f"KHÔNG dùng được: {err}")

    write("\n=== 6. MẤT TIN? Gửi NHANH 3 tin từ Zalo, đang chờ... ===")
    write("   (gửi 3 tin liên tiếp thật nhanh: 1, 2, 3)")
    received = 0
    for _ in range(3):
        t = await client.get_updates(20)
        if t is not None and t.message is not None and t.message.text:
            received += 1
    _row("nhận được", f"{received}/3 tin")
    _row("kết luận", "KHÔNG mất tin - hàng chờ có đệm" if received == 3 else f"MẤT {3 - received}/3 tin")

    write("\n=== 7. Rate limit: bắn 10 tin liên tiếp ===")
    ok = 0
    loi = ""
    started = time.monotonic()
    for i in range(1, 11):
        try:
            await client.send_message(chat_id, f"Thử nhịp {i}/10", None)
            ok += 1
        except LoiZaloBotApi as err:
            loi = str(err)
            break
    _row("gửi thành công", f"{ok}/10 trong {int((time.monotonic() - started) * 1000)}ms")
    _row("lỗi (nếu có)", loi or "không")

    write("\nXong. Câu hỏi CÒN LẠI phải tự thử: bot có nhắn được cho người")
    write("CHƯA từng nhắn cho nó không (nhờ một người khác đừng nhắn gì, rồi")
    write("thử gửi vào id của họ) - đây là điều kiện sống của tính năng lịch hẹn.\n")
    return 0


def main(
    argv: list[str] | None = None,
    *,
    run: Callable[[BotApiClient], Awaitable[int]] = probe,
) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        sys.stderr.write(
            "Không nhận token qua tham số dòng lệnh. Đặt biến môi trường PEMA_ZALO_BOT_PROBE_TOKEN.\n"
        )
        return 2
    token = next((os.environ[n] for n in ENV_NAMES if os.environ.get(n)), "")
    if not token:
        sys.stderr.write(
            "Thiếu token. Đặt PEMA_ZALO_BOT_PROBE_TOKEN (token của MỘT bot thử, không phải bot thật).\n"
        )
        return 1
    client = tao_zalo_bot_client(token)

    async def _run() -> int:
        try:
            return await run(client)
        except LoiZaloBotApi as err:
            sys.stderr.write(f"\nHỎNG: {err}\n")
            return 1
        finally:
            await client.aclose()

    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
