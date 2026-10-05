# ported from: src/agent/tools/get-datetime-tool.ts
"""Exact time for the agent: the system prompt only carries the date (to keep the prompt cache), so when the
minute is needed the model calls this tool. No parameter: the time zone comes from ``BOT_TIMEZONE``, the
users of
the bot are all in the same zone.

Forced deviation: the Vercel AI SDK ``tool()`` becomes ``FunctionTool``."""

from __future__ import annotations

from pema.agent.tools.function_tool import FunctionTool, NoArgs
from pema.config.runtime_tuning_settings import bot_time_zone
from pema.shared.current_datetime import get_date_time_parts

DESCRIPTION = (
    "Lấy ngày giờ hiện tại chính xác (ngày, giờ phút, thứ trong tuần, múi giờ). Dùng khi cần giờ hiện tại, "
    "tính khoảng cách thời gian, hoặc trả lời câu hỏi về hôm nay/ngày mai. Thứ trong tuần trong kết quả là "
    "chính xác tuyệt đối - dùng nguyên văn, không tự suy lại từ ngày."
)


def create_get_datetime_tool() -> FunctionTool[NoArgs]:
    async def handler(_args: NoArgs) -> object:
        p = get_date_time_parts(bot_time_zone())
        return f"Bây giờ là {p.time} {p.weekday}, ngày {p.date} (múi giờ {p.timezone})."

    return FunctionTool(name="get_datetime", description=DESCRIPTION, input_model=NoArgs, handler=handler)
