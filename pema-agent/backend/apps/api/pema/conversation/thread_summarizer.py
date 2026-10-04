# ported from: src/conversation/thread-summarizer.ts
"""Memory lớp 2 (compaction thu nhỏ của OpenClaw): tin cũ rớt khỏi cửa sổ replay được gộp dần vào 1
summary per thread, inject lại vào system prompt - hội thoại dài vẫn giữ được mạch mà không phình prompt.

Chạy SAU khi bot đã trả lời (fire-and-forget) nên không làm chậm phản hồi; lỗi summary không được phá lượt
chat.

Forced deviations:

* Vercel AI SDK ``streamText`` is not available. The model call is the ``TextGenerator`` seam of
  ``pema_contracts.agent_turn`` (single-shot completion, no tools), implemented by D1 over the configured
  provider. D1 is also the place that keeps the two properties the original documented for the call:
  STREAMING (the router sits behind Cloudflare, which cuts a request with 524 when no byte arrives in 100 s;
  a failure here is SILENT because ``maybe_summarize_thread`` swallows errors, so the bot's long-term memory
  would erode unseen) and ``maxRetries: 1``. ``run_summary`` is ``chayTomTat``: it asks for
  ``max_output_tokens=1024`` and maps the generator's ``truncated`` flag (``finishReason === "length"``) to
  ``SummaryResult.truncated``;
* the default generator (``resolveLanguageModel`` imported lazily to dodge an import cycle) becomes the
  ``text_generator`` given to ``ThreadSummarizer``; without one and without an explicit ``generate`` the
  summariser logs once and does nothing;
* SQLite sync -> SQLAlchemy async + Postgres (``clinic_id`` + RLS).

Clinic note: the summary is built from the history of the thread, which holds patient text; the generator is
the configured model of the clinic (a local model or the provider the owner chose), the same as the turn
itself. This module does not know the policy, so a caller under ``patient_channel`` MUST pass
``prompt_filter`` (the PII mask of the policy, ``PolicyHooks.mask_text``): the prompt is built from the
RAW history (names, phone numbers) and the filter is applied to the whole prompt before any model call. A
filter that raises means NO model call (fail closed). Package G found the first version of the worker calling
this without a filter (SECURITY-REVIEW-AI01, SEC-01).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.conversation.thread_store import ThreadStoreImpl
from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger
from pema_contracts.agent_turn import TextGenerator

_log = create_logger("thread-summarizer")

# Tin thứ N mới nhất - mọi tin có id nhỏ hơn là "ngoài cửa sổ replay".
_WINDOW_START = text(
    """
    SELECT id FROM agent.history WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id =
    :thread_id ORDER BY id DESC LIMIT 1 OFFSET :offset
    """
)

_BACKLOG = text(
    """
    SELECT id, role, sender_name, content FROM agent.history
    WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id
      AND id > :covers_to AND id < :window_start
    ORDER BY id
    """
)

SUMMARY_MAX_OUTPUT_TOKENS = 1024


@dataclass(frozen=True)
class BacklogRow:
    id: int
    role: str
    sender_name: str | None
    content: str


@dataclass(frozen=True)
class Backlog:
    backlog: list[BacklogRow]
    old_summary: str
    covers_to: int


@dataclass(frozen=True)
class SummaryResult:
    """``truncated`` = LLM chạm ``maxOutputTokens`` (finishReason 'length') -> bản tóm tắt bị CẮT CỤT giữa
    chừng. KHÔNG được lưu bản cụt: nó sẽ ghi đè summary tốt + đẩy ``covers_to`` tiến, đánh dấu đám tin đó
    "đã phủ" nên KHÔNG BAO GIỜ tóm tắt lại - mất trí nhớ im lặng, vĩnh viễn. Trần mềm trong prompt khiến
    ca này hiếm; đây là lưới đỡ cuối."""

    text: str
    truncated: bool


SummaryGenerator = Callable[[str], Awaitable[SummaryResult]]


async def run_summary(generator: TextGenerator, prompt: str) -> SummaryResult:
    """Gọi model tóm tắt rồi ánh xạ ``finishReason`` -> ``truncated`` (``chayTomTat``). Tách khỏi nơi dùng
    để test được CỬA PHÁT HIỆN bản cụt bằng generator giả mà không cần provider thật: mọi test khác tiêm
    sẵn ``truncated`` nên đổi nhầm cửa này là hồi quy CÂM."""
    generated = await generator.generate_text(prompt, max_output_tokens=SUMMARY_MAX_OUTPUT_TOKENS)
    # ``truncated`` = chạm cap 1024 -> bản cụt. Báo lên để caller KHÔNG lưu (giữ summary cũ còn nguyên vẹn).
    return SummaryResult(text=generated.text.strip(), truncated=generated.truncated)


# Các MỤC cố định của bản tóm tắt, hợp domain chat cá nhân trên Zalo.  Vì sao mục cố định thay vì "viết một
# đoạn tự do" (học từ COMPACTION_INSTRUCTION của DeepSeek Harness): prompt tự do để LLM tự chọn giữ gì, và
# qua nhiều lần gộp nó lặng lẽ đánh rơi một khía cạnh (vd quên "việc đã hứa"). Ép điền đủ mục, mục rỗng ghi
# "(không có)" thì mất mát trở nên NHÌN THẤY được thay vì im lặng. KHÔNG bê bộ mục coding của dsh
# (Files/Code/Errors) - vô nghĩa với bot chat.
SUMMARY_SECTIONS = [
    "NGƯỜI & QUAN HỆ: tên, vai trò, cách xưng hô, quan hệ với nhau",
    "QUYẾT ĐỊNH & ĐÃ HỨA: điều đã chốt, việc bot/người dùng đã hứa làm",
    "SỞ THÍCH & THÓI QUEN: điều thích/ghét, ràng buộc, cách muốn được đối xử",
    "VIỆC ĐANG DỞ: bối cảnh hiện tại, việc chưa xong, đang chờ gì",
    "CÂU HỎI TREO: điều người dùng hỏi mà chưa được trả lời trọn",
]


def _speaker(message: BacklogRow) -> str:
    if message.role == "assistant":
        return "Bot"
    return message.sender_name if message.sender_name is not None else "Người dùng"


def build_summary_prompt(old_summary: str, backlog: list[BacklogRow]) -> str:
    lines = [f"{_speaker(m)}: {m.content}" for m in backlog]
    return "\n".join(
        [
            "Bạn đang duy trì bản tóm tắt một cuộc hội thoại Zalo dài để bot nhớ mạch chuyện.",
            "Gộp TÓM TẮT HIỆN TẠI và ĐOẠN HỘI THOẠI MỚI thành MỘT bản tóm tắt mới, tiếng Việt.",
            "",
            "Xuất ĐÚNG các mục sau theo thứ tự, mỗi mục vài gạch đầu dòng ngắn:",
            *[f"- {m}" for m in SUMMARY_SECTIONS],
            "",
            "LUẬT:",
            '- Mục nào không có thông tin thì ghi "(không có)" - TUYỆT ĐỐI không bỏ mục.',
            "- Giữ NGUYÊN VĂN chỗ từ ngữ quan trọng: tên riêng, con số, ngày giờ, lời hứa.",
            "- Nếu người dùng ĐÍNH CHÍNH điều gì (vd tên, thông tin), ghi lại bản đã sửa.",
            "- Đã có TÓM TẮT HIỆN TẠI: giữ fact còn đúng, bỏ fact đã cũ/bị thay, HỢP NHẤT thông",
            "  tin mới vào - KHÔNG chép nguyên bản cũ, KHÔNG để hai bản chồng nhau.",
            "- Bỏ chào hỏi xã giao. Chỉ trả về nội dung tóm tắt, không mở bài, không kết luận.",
            "- Toàn bản GIỮ DƯỚI ~400 từ: ưu tiên fact quan trọng, cắt bớt chi tiết vụn. Thà",
            "  gọn mà đủ mục còn hơn dài rồi bị cắt cụt giữa chừng.",
            "",
            f"TÓM TẮT HIỆN TẠI:\n{old_summary or '(chưa có)'}",
            "",
            f"ĐOẠN HỘI THOẠI MỚI:\n{chr(10).join(lines)}",
        ]
    )


class ThreadSummarizer:
    def __init__(
        self,
        db: ClinicDatabase,
        threads: ThreadStoreImpl | None = None,
        text_generator: TextGenerator | None = None,
    ) -> None:
        self._db = db
        self._threads = threads or ThreadStoreImpl(db)
        self._text_generator = text_generator

    async def collect_summary_backlog(self, clinic_id: UUID, account_id: str, thread_id: str) -> Backlog:
        """Phần thuần (test được không cần LLM): gom tin đã rớt khỏi window mà summary chưa phủ."""
        stored = await self._threads.get_thread_summary(clinic_id, account_id, thread_id)
        old_summary, covers_to = stored.summary, stored.covers_to_message_id

        scope = {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id}
        async with self._db.session(clinic_id) as session:
            window_start = (
                await session.execute(
                    _WINDOW_START, {**scope, "offset": get_tuning_int("HISTORY_CONTEXT_LIMIT") - 1}
                )
            ).scalar()
            if window_start is None:
                return Backlog(backlog=[], old_summary=old_summary, covers_to=covers_to)

            rows = (
                (
                    await session.execute(
                        _BACKLOG, {**scope, "covers_to": covers_to, "window_start": int(window_start)}
                    )
                )
                .mappings()
                .all()
            )
        backlog = [
            BacklogRow(id=int(r["id"]), role=r["role"], sender_name=r["sender_name"], content=r["content"])
            for r in rows
        ]
        return Backlog(backlog=backlog, old_summary=old_summary, covers_to=covers_to)

    async def maybe_summarize_thread(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        generate: SummaryGenerator | None = None,
        prompt_filter: Callable[[str], str] | None = None,
    ) -> bool:
        """Gọi sau mỗi lượt trả lời. Chỉ tốn 1 LLM call khi backlog đủ lớn.

        ``prompt_filter``: applied to the whole prompt right before the model call (the PII mask of
        ``patient_channel``)."""
        try:
            collected = await self.collect_summary_backlog(clinic_id, account_id, thread_id)
            if len(collected.backlog) < get_tuning_int("SUMMARY_TRIGGER_MESSAGES"):
                return False

            generator = generate or self._default_generator()
            if generator is None:
                _log.warning(
                    "Chưa cấu hình model tóm tắt - bỏ qua", account_id=account_id, thread_id=thread_id
                )
                return False

            prompt = build_summary_prompt(collected.old_summary, collected.backlog)
            if prompt_filter is not None:
                prompt = prompt_filter(prompt)
            result = await generator(prompt)
            if result.truncated:
                # Bản cụt: KHÔNG ghi đè, KHÔNG tiến covers_to. Giữ summary cũ, lần sau thử lại (backlog vẫn
                # còn nguyên vì covers_to đứng yên).
                _log.warning(
                    "Tóm tắt bị cắt cụt ở token cap - bỏ, giữ bản cũ",
                    account_id=account_id,
                    thread_id=thread_id,
                )
                return False
            if not result.text:
                return False

            await self._threads.set_thread_summary(
                clinic_id, account_id, thread_id, result.text, collected.backlog[-1].id
            )
            _log.debug(
                "Đã gộp tin cũ vào summary",
                account_id=account_id,
                thread_id=thread_id,
                folded=len(collected.backlog),
            )
            return True
        except Exception as err:
            # Summary hỏng không được ảnh hưởng lượt chat - lần sau thử lại.
            _log.warning(
                "Tóm tắt thread thất bại - bỏ qua", account_id=account_id, thread_id=thread_id, err=err
            )
            return False

    def _default_generator(self) -> SummaryGenerator | None:
        generator = self._text_generator
        if generator is None:
            return None

        async def generate(prompt: str) -> SummaryResult:
            return await run_summary(generator, prompt)

        return generate
