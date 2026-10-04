# ported from: src/agent/agent-loop.ts
"""Run ONE agent turn: history + the whole batch of new messages (images included) -> the LLM decides to call
tools (react, send a file, tag ...) -> the final text to send back.

``run_agent_turn`` is ``runAgentTurn``; ``DefaultAgentEngine`` is the
``pema_contracts.agent_turn.AgentEngine`` the channel turn processor (C2) and the scheduler (S) call. The
messages of the turn are ALREADY in the database before this runs (the channel records them on receipt), so
the history builder FILTERS them out, otherwise the model reads the question twice; and it reads the DB with a
surplus equal to the number of rows about to be filtered, otherwise the history window shrinks silently with
the batch size.

Forced deviations from zalo-agent (the reasoning of the comments is kept, translated):

* Vercel ``streamText`` -> ``pema.agent.stream_text_result.chay_stream`` (own tool loop; same step,
  ``stopWhen``, ``prepareStep``, ``onStepFinish``, ``maxRetries`` and total timeout semantics).
* ``(api, account, batch, trace, resolveModel, isolated, layTinChen, layIdDangCho, ghiNhanDaGui)`` ->
  ``AgentTurnRequest`` + ``TurnCallbacks`` (contracts); ``ParsedMessage`` -> ``InboundMessage``; the zca-js
  ``api`` is replaced by ``ToolContext.channel`` (the running ``ChannelPort`` of the account); every store is
  injected (``AgentEngineDeps``) and async; the model comes from an injectable ``resolve_model``.
* The engine raises ONLY ``AgentTurnError`` (the kind already classified by ``phan_loai_loi_provider``, the
  original exception in ``__cause__``) so the callers never import ``pema.agent`` nor an SDK type.
* The turn row of ``usage`` is opened here (``UsageStore.open_agent_turn``, unless the request carries a
  ``turn_id`` the caller already opened) so a failed turn keeps an id: it is returned in
  ``AgentTurnResult.turn_id`` and in ``AgentTurnError.turn_id``. Finishing the row and saving the trace stay
  with the caller, who owns ``TurnCallbacks.trace`` (``finishAgentTurn`` + ``saveTurnTrace`` run at most ONCE
  per turn there, see ``message-turn-processor.ts``).

Policy hooks (``pema_contracts.policy``), the call sites of package D1 (CONTRACTS-AI01 section 3):

* ``verify_identity``: once at the start of a turn answering a person, only when the profile demands it; the
  answer is carried in ``PolicyContext.identity_verified`` / ``patient_id`` (the tools read it from
  ``ToolContext.policy`` before naming a patient, an appointment or a medicine);
* ``before_llm``: BEFORE any model call, on the batch, and again on every message injected mid-turn. A
  ``HAND_OFF`` stops the turn at once (``AgentTurnResult.handed_off``); the masked texts it returns replace
  the text the model (and the tools) see;
* ``after_llm``: on the final text (the normal answer and the wrap-up), before it is returned for delivery.
``filter_tool_keys`` is called by the tool registry (D4), ``allow_memory_write`` by ``save_memory`` (D4),
``on_outbound``/``check_job``/``proactive_cap`` by the channel pipeline and the scheduler (C2, S).
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from pema.agent.agent_loop_conditions import (
    can_luot_chot,
    hit_step_limit,
    is_empty_router_completion,
    nhan_ly_do_dung,
    vuot_tran_token,
)
from pema.agent.agent_step_observer import tao_quan_sat_step
from pema.agent.agent_step_trace import summarize_step
from pema.agent.agent_turn_content import (
    ImageContextMode,
    ImageDownloader,
    TurnContentDeps,
    build_turn_messages,
)
from pema.agent.history_to_model_messages import StoredImageLoader
from pema.agent.llm_provider import (
    ModelOverrideLike,
    ThreadSession,
    resolve_language_model,
    resolve_reasoning_effort,
    resolve_reasoning_options,
)
from pema.agent.mid_turn_injection import dung_tin_chen_trong_ngan_sach, tao_bo_chen_tin
from pema.agent.model_types import ChatModel, ModelMessage, ModelUsage, RawStep
from pema.agent.model_vision_detection import mark_model_no_vision
from pema.agent.persona_prompt import PromptMemory, build_system_prompt
from pema.agent.provider_error_classifier import giay_cho_lai, ma_http_cua, phan_loai_loi_provider
from pema.agent.safe_turn_error import to_turn_error
from pema.agent.stream_text_result import StreamTextResult, chay_stream, step_count_is
from pema.agent.token_estimate import (
    TOKEN_MOI_ANH_THEO_CO,
    CoAnh,
    dem_ky_tu_input_day_du,
    ngan_sach_an_toan,
    so_sanh_uoc_luong,
    uoc_luong_token_tin_nhan,
)
from pema.agent.tool_loop_guard import ToolLoopGuard
from pema.agent.tool_loop_guard_thresholds import NguongGuard, nguong_theo_tran_step
from pema.agent.trim_context_to_budget import cat_ngu_canh_theo_ngan_sach
from pema.agent.vision_rejection_fallback import has_image_parts, is_image_rejection_error
from pema.config.runtime_settings_store import set_settings_clinic
from pema.config.runtime_tuning_settings import get_tuning, get_tuning_bool, get_tuning_int
from pema.config.runtime_vision_settings import is_sidecar_configured
from pema.shared.logger import create_logger
from pema_contracts.agent_turn import (
    AgentTurnRequest,
    AgentTurnResult,
    StepTrace,
    TokenUsage,
    TurnCallbacks,
    TurnSource,
)
from pema_contracts.agents import AccountConfig, AccountStore, AgentProfile, AgentStore
from pema_contracts.channel import (
    ChannelCapabilities,
    ChannelPort,
    ChannelRegistry,
    InboundMessage,
)
from pema_contracts.conversation import (
    ImageDescriptionStore,
    MemoryContextItem,
    StoredMessage,
    ThreadSummary,
)
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    BeforeLlmAction,
    BeforeLlmDecision,
    PermissivePolicyHooks,
    PolicyContext,
    PolicyHooks,
    effective_profile_key,
)
from pema_contracts.tools import AgentTool, ToolContext, ToolGroup, ToolRegistry
from pema_contracts.turn_errors import AgentTurnError, ProviderErrorKind

log = create_logger("agent-loop")

# Re-exported so tests and every old call site import them from "agent_loop" as before.
__all__ = [
    "ROUTER_DOWN_REPLY",
    "STEP_LIMIT_REPLY",
    "AgentEngineDeps",
    "DefaultAgentEngine",
    "ModelResolver",
    "can_luot_chot",
    "hit_step_limit",
    "is_empty_router_completion",
    "nhan_ly_do_dung",
    "run_agent_turn",
    "vuot_tran_token",
]

TECHNICAL_ERROR_REPLY = (
    "Mình đang gặp trục trặc kỹ thuật nên chưa trả lời được tin này, bạn nhắn lại giúp mình sau ít phút nhé."
)
"""The sentence for a bot that broke mid-way (``TECHNICAL_ERROR_REPLY`` of ``send-reply-in-parts.ts``, package
C2's file: the same text, kept here only so this module does not import the channel pipeline). Staying silent
and leaving the sender hanging is the worst behaviour: they cannot tell whether to wait or write again."""

ROUTER_DOWN_REPLY = TECHNICAL_ERROR_REPLY
"""The message when the router failed BOTH times: silently leaving the sender hanging is the worst. One
sentence shared with the error branch of the account manager so the sender does not have to guess whether two
different notices mean two different things."""

STEP_LIMIT_REPLY = (
    "Mình tra hơi nhiều bước mà vẫn chưa gom đủ để trả lời cho chắc. Anh/chị hỏi lại gọn hơn một chút giúp "
    "mình nhé, ví dụ chỉ một mục hoặc một nguồn thôi."
)
"""Used when the steps ran out AND the wrap-up call produced no text either. It says plainly that it is not
done instead of staying silent or sending an internal narration sentence: the sender can still ask again."""

WRAP_UP_PROMPT = (
    "Bạn đã hết lượt gọi công cụ. Dựa vào những gì đã thu thập được ở trên, hãy trả lời người dùng NGAY BÂY "
    "GIỜ. Nói rõ phần nào chắc chắn, phần nào còn thiếu vì chưa tra xong - đừng bịa cho đủ. Không kể lể tiến "
    "trình, không hứa sẽ tra thêm."
)


class ModelResolver(Protocol):
    """``resolveModel`` of the original: ``resolve_language_model`` by default, a fake in tests."""

    def __call__(
        self, override: ModelOverrideLike | None = None, thread: ThreadSession | None = None, /
    ) -> ChatModel: ...


class EngineConversation(Protocol):
    """The slice of ``ConversationStore`` the engine reads: any full store satisfies it, a test fake need only
    implement these."""

    async def get_recent_messages(
        self, clinic_id: UUID, account_id: str, thread_id: str, limit: int | None = None
    ) -> list[StoredMessage]: ...

    async def get_memories_for_context(
        self, clinic_id: UUID, *, account_id: str, thread_id: str, sender_id: str, is_group: bool
    ) -> list[MemoryContextItem]: ...

    async def get_thread_summary(self, clinic_id: UUID, account_id: str, thread_id: str) -> ThreadSummary: ...

    async def get_thread_context_epoch(self, clinic_id: UUID, account_id: str, thread_id: str) -> int: ...

    async def open_agent_turn(
        self, clinic_id: UUID, account_id: str, thread_id: str, source: TurnSource = ...
    ) -> int: ...


@dataclass
class AgentEngineDeps:
    """Everything the engine needs from the outside (all injected, nothing global except tuning)."""

    accounts: AccountStore
    agents: AgentStore
    conversation: EngineConversation
    image_descriptions: ImageDescriptionStore
    tools: ToolRegistry
    channels: ChannelRegistry
    load_image: StoredImageLoader
    download_image: ImageDownloader
    policy: PolicyHooks = field(default_factory=PermissivePolicyHooks)
    resolve_model: ModelResolver = resolve_language_model
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    """Waits of the loop (backoff, ``Retry-After``): tests inject an instant one."""
    retry_initial_delay_s: float = 2.0
    """First backoff of ``maxRetries`` (the SDK's 2 s); tests pass 0."""


def _log_stream_error(error: BaseException) -> None:
    """The ``onError`` of ``streamText``, replacing the SDK default.

    The default of ai@7.0.37 was a bare ``console.error(error)``: two harms at once. That line did NOT go
    through the logger so it never reached the log file (exactly when it is needed most), and it printed the
    RAW error so the ``requestBodyValues`` of an ``APICallError`` (the whole system prompt + conversation +
    base64 images) landed on stdout. In the clinic that is patient conversation text. The errors go through
    the logger and its safe serializer only.

    WARNING level, not DEBUG: a failed attempt is the only trace of a transient fault when a retry then
    succeeds. A turn that failed for good also gets an ERROR line with the classification; the two complement
    each other.
    """
    log.warning("model call failed", err=error)


def _image_quality() -> CoAnh:
    value = str(get_tuning("ZALO_IMAGE_QUALITY"))
    return value if value in TOKEN_MOI_ANH_THEO_CO else "normal"  # type: ignore[return-value]


def _tokens_per_image() -> int:
    return TOKEN_MOI_ANH_THEO_CO[_image_quality()]


def _usage_of(total: ModelUsage, steps: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=total.input_tokens or 0,
        output_tokens=total.output_tokens or 0,
        total_tokens=total.total_tokens or 0,
        steps=steps,
    )


class Masker:
    """The PII mask of the policy applied to EVERYTHING a turn shows the model besides the batch text that
    ``before_llm`` already masked: history lines, the sender name, durable facts, the thread summary and tool
    results (CONTRACTS section 3, policy hook call sites; the integration note of package P).

    ``PolicyHooks`` itself has no such method, so the real hooks of package P expose two OPTIONAL ones next to
    the eight, ``mask_text(ctx, text)`` and ``mask_name(ctx, name)``, and this class uses them when present.
    ``PermissivePolicyHooks`` has neither: nothing is masked (``staff_assistant``). The hook itself decides
    whether the profile masks (it is a no-op when it does not); the mask store is the process memory of the
    turn's chat, so ``before_llm`` and ``after_llm`` must run in the SAME worker process.
    """

    def __init__(self, policy: PolicyHooks, ctx: PolicyContext) -> None:
        self._policy: Any = policy
        self._ctx = ctx

    def text(self, value: str) -> str:
        fn = getattr(self._policy, "mask_text", None)
        return str(fn(self._ctx, value)) if callable(fn) and value else value

    def name(self, value: str) -> str:
        fn = getattr(self._policy, "mask_name", None)
        if callable(fn) and value:
            return str(fn(self._ctx, value))
        return self.text(value)

    def message(self, m: StoredMessage) -> StoredMessage:
        return m.model_copy(
            update={
                "content": self.text(m.content),
                "sender_name": None if m.sender_name is None else self.name(m.sender_name),
            }
        )


def _for_model(
    batch: Sequence[InboundMessage], decision: BeforeLlmDecision, masker: Masker
) -> list[InboundMessage]:
    """The batch as the model must see it: the texts the policy masked replaced, the sender names masked."""
    out: list[InboundMessage] = []
    for m in batch:
        update: dict[str, object] = {}
        if m.msg_id in decision.masked_text_by_msg_id:
            update["text"] = decision.masked_text_by_msg_id[m.msg_id]
        if m.sender_name:
            update["sender_name"] = masker.name(m.sender_name)
        out.append(m.model_copy(update=update) if update else m)
    return out


def _default_caps(account: AccountConfig) -> ChannelCapabilities:
    """Capabilities when the channel of the account is not running in this process (a scheduled turn of an
    account that is stopped): nothing the channel could do is promised."""
    return ChannelCapabilities(channel=account.channel, can_send_proactive=False)


@dataclass
class _Progress:
    """What a turn did so far, readable by ``run_agent_turn`` even when the turn is cut short."""

    usage: ModelUsage = field(default_factory=ModelUsage)
    steps: int = 0
    hand_off: BeforeLlmDecision | None = None


class _MidTurnHandOff(BaseException):
    """Raised at the step boundary when a message injected mid-turn made the policy hand the conversation off:
    the model is NOT called again and whatever it wrote so far is NOT used. A ``BaseException`` so the repair
    branches (``except Exception``) never mistake it for a provider failure."""


async def run_agent_turn(
    deps: AgentEngineDeps, request: AgentTurnRequest, callbacks: TurnCallbacks | None = None
) -> AgentTurnResult:
    """Run one agent turn (``runAgentTurn``). Raises ``AgentTurnError`` for every failure."""
    cb = callbacks if callbacks is not None else TurnCallbacks()
    clinic_id = request.clinic_id
    # The synchronous readers (tuning, LLM settings) are keyed by clinic through a ContextVar; every asyncio
    # task has its own copy so concurrent turns of different clinics do not interfere.
    set_settings_clinic(clinic_id)

    account = await deps.accounts.get_account(clinic_id, request.account_id)
    if account is None:
        raise AgentTurnError(ProviderErrorKind.CONFIG, "account not found for this clinic")
    agent = await deps.agents.get_agent_for_account(clinic_id, account)

    # The latest message represents the turn: tools (reaction, quote) act on this one.
    latest = request.batch[-1]
    turn_id: int | None = request.turn_id
    progress = _Progress()
    try:
        if turn_id is None:
            turn_id = await deps.conversation.open_agent_turn(
                clinic_id, account.id, latest.thread_id, request.source
            )
        return await _run_turn(deps, request, cb, account, agent, turn_id, progress)
    except _MidTurnHandOff:
        # A message that arrived mid-turn tripped the policy: whatever the model wrote is NOT used.
        decision = progress.hand_off
        log.info(
            "turn handed off mid-turn",
            reason=decision.reason if decision else None,
            flags=len(decision.red_flags) if decision else 0,
        )
        return AgentTurnResult(
            text="",
            usage=_usage_of(progress.usage, progress.steps),
            turn_id=turn_id,
            handed_off=True,
            hand_off_reason=(decision.reason if decision else None) or "hand_off",
        )
    except AgentTurnError:
        raise
    except Exception as err:
        raise to_turn_error(err, turn_id=turn_id) from err


async def _run_turn(
    deps: AgentEngineDeps,
    request: AgentTurnRequest,
    cb: TurnCallbacks,
    account: AccountConfig,
    agent: AgentProfile,
    turn_id: int,
    progress: _Progress,
) -> AgentTurnResult:
    clinic_id = request.clinic_id
    isolated = request.isolated
    batch = list(request.batch)
    latest = batch[-1]
    trace: list[StepTrace] = cb.trace

    channel: ChannelPort | None = deps.channels.get_running(clinic_id, account.id)
    caps = channel.capabilities() if channel is not None else _default_caps(account)

    profile = DEFAULT_PROFILES[effective_profile_key(account.policy_profile, agent.policy_profile)]
    ctx = PolicyContext(
        clinic_id=clinic_id,
        account_id=account.id,
        agent_id=agent.id,
        channel=account.channel,
        thread_id=latest.thread_id,
        profile=profile,
        isolated=isolated,
        request_id=request.request_id,
    )
    # Identity: only for a turn answering a PERSON, and only when the profile demands it. The tools read the
    # answer from ``ToolContext.policy`` before they name a patient, an appointment or a medicine.
    if not isolated and profile.require_identity_verification:
        identity = await deps.policy.verify_identity(ctx, account.channel, latest.sender_id)
        ctx = dataclasses.replace(ctx, identity_verified=identity.verified, patient_id=identity.patient_id)

    # Policy BEFORE any model call (red flags, PII masking). A hand-off means the model is never called.
    decision = await deps.policy.before_llm(ctx, batch)
    if decision.action is BeforeLlmAction.HAND_OFF:
        log.info("turn handed off before the model", reason=decision.reason, flags=len(decision.red_flags))
        return AgentTurnResult(
            text="", turn_id=turn_id, handed_off=True, hand_off_reason=decision.reason or "hand_off"
        )
    mask_token = decision.mask_token
    masker = Masker(deps.policy, ctx)
    model_batch = _for_model(batch, decision, masker)
    model_latest = model_batch[-1]

    # Read ONCE for the whole turn: the router session key must be the same at every step, the wrap-up call
    # included. Re-reading mid-turn changes the session if someone wipes the context right then: it loses the
    # cache and the cause is hard to trace.
    context_epoch = await deps.conversation.get_thread_context_epoch(clinic_id, account.id, latest.thread_id)

    # The isolated session does NOT call history / memory / summary (not just ignores the result): a scheduled
    # job must not read the thread's live conversation, to avoid mixing "what the user is talking about" with
    # "a job reporting at 3 a.m.". The messages of this turn and the ones waiting in the batcher are BOTH
    # already in the history and both about to be filtered: ask for exactly that many extra rows, or the
    # window shrinks silently: a batch of 5 leaves the model 15 old messages instead of 20, a batch at the
    # ceiling of 32 leaves 0, and the bot walks into the turn not knowing what it just answered.
    tran_lich_su = get_tuning_int("HISTORY_CONTEXT_LIMIT")
    id_dang_cho: list[int] = (
        [] if isolated or cb.pending_history_ids is None else [int(i) for i in await cb.pending_history_ids()]
    )
    history: list[StoredMessage] = (
        []
        if isolated
        else [
            masker.message(m)
            for m in await deps.conversation.get_recent_messages(
                clinic_id, account.id, latest.thread_id, tran_lich_su + len(batch) + len(id_dang_cho)
            )
        ]
    )
    # Effective token ceiling: the agent's own wins over the shared setting (same as max steps and reasoning
    # effort). It lives on the agent because the ceiling depends on the MODEL's window.
    tran_token = (
        agent.context_window if agent.context_window is not None else get_tuning_int("LLM_CONTEXT_WINDOW")
    )
    # Computed ONCE here and shared by ``stop_when``, the guard thresholds and the stop-reason log: those
    # three must talk about the same number, and each used to re-read ``agent.max_steps ?? tuning``.
    tran_step = agent.max_steps if agent.max_steps is not None else get_tuning_int("LLM_MAX_STEPS")

    content_deps = TurnContentDeps(
        clinic_id=clinic_id,
        load_image=deps.load_image,
        download_image=deps.download_image,
        image_descriptions=deps.image_descriptions,
    )
    built = await build_turn_messages(
        history=history,
        batch=model_batch,
        id_bo_qua=id_dang_cho,
        tran_lich_su=tran_lich_su,
        override=agent,
        allowlist=account.allowlist,
        tran_token=tran_token,
        deps=content_deps,
    )
    messages: list[ModelMessage] = built.messages
    image_mode: ImageContextMode = built.image_mode
    if built.da_cat is not None:
        log.warning(
            "context exceeded the token budget: trimmed before calling the model",
            tran_token=tran_token,
            **dataclasses.asdict(built.da_cat),
        )

    # Memory: durable facts (filtered by the privacy rule) + the summary of the older part of the
    # conversation.
    memory = PromptMemory(facts=[], thread_summary="")
    if not isolated:
        memory = PromptMemory(
            facts=[
                item.model_copy(update={"content": masker.text(item.content)})
                for item in await deps.conversation.get_memories_for_context(
                    clinic_id,
                    account_id=account.id,
                    thread_id=latest.thread_id,
                    sender_id=latest.sender_id,
                    is_group=latest.is_group,
                )
            ],
            thread_summary=masker.text(
                (await deps.conversation.get_thread_summary(clinic_id, account.id, latest.thread_id)).summary
            ),
        )

    # ``trace`` is the CALLER's list shared by EVERY run in the turn (the glitch retry and the rebuild without
    # pixels append to it): when things break one needs to see both runs. Each run numbers its steps from 1,
    # so the RUN is recorded too: without it the trace reads 1,1,2,2,3,3 and looks like a model looping.
    lan_chay = 1

    # Tool-loop guard: built ONCE per turn but ``dat_lai()`` on every ``lan_chay += 1`` (retry of an empty
    # completion, rebuild without pixels): a new run is a new context and must not carry the previous one's
    # sins. A LOCAL of this function, not module state: many threads run in parallel, each turn needs its own
    # counters. ``group == read`` of the catalogue is the set of read-only tools: used instead of writing a
    # second list that would drift from the catalogue.
    group_by_key = {spec.key: spec.group for spec in deps.tools.definitions()}
    guard = ToolLoopGuard(
        nguong_theo_tran_step(
            NguongGuard(
                chan_loi_giong_het=get_tuning_int("TOOL_LOOP_SAME_ARGS_BLOCK"),
                chan_cung_tool_loi=get_tuning_int("TOOL_LOOP_SAME_TOOL_BLOCK"),
                chan_khong_tien_trien=get_tuning_int("TOOL_LOOP_NO_PROGRESS_BLOCK"),
            ),
            tran_step,
        ),
        lambda name: group_by_key.get(name) is ToolGroup.READ,
    )
    # ``lay_lan_chay`` is a FUNCTION, not a number: ``lan_chay`` grows mid-turn; passing the value would label
    # the traces of later runs with the first run's number.
    quan_sat_step = tao_quan_sat_step(guard=guard, trace=trace, lay_lan_chay=lambda: lan_chay)

    # Mid-turn messages ALREADY PULLED from the waiting queue in this turn. They MUST be kept HERE and not
    # only inside the loop's own message list: the fetch REMOVED them from the queue so there is no way to get
    # them back, and every repair branch (retry without pixels, 429, context overflow, empty-completion retry)
    # AND the wrap-up call rebuild the context from ``messages`` of THIS function, not from the loop's list.
    # Dropping this list would lose messages exactly in the long turns, the only ones long enough for the
    # person to write again: the turn that hits the step ceiling goes to the wrap-up call, and the wrap-up
    # call is what produces the answer sent out; the sender would get an answer composed for the OLD request
    # while the model, told to "answer NOW", has no way to say it is ignoring a request. Same ownership rule
    # as the ``trace`` list: whatever must survive several runs is held by this function.
    tin_chen_da_keo: list[InboundMessage] = []

    async def lay_tin_chen() -> Sequence[InboundMessage]:
        nonlocal mask_token
        fetch = cb.fetch_injected_messages
        moi = list(await fetch()) if fetch is not None else []
        if not moi:
            return []
        # The policy sees every message BEFORE the model does, also the ones that arrive mid-turn.
        mid = await deps.policy.before_llm(ctx, moi)
        if mid.action is BeforeLlmAction.HAND_OFF:
            progress.hand_off = mid
            return []
        if mid.mask_token is not None:
            mask_token = mid.mask_token
        masked = _for_model(moi, mid, masker)
        # Recorded IMMEDIATELY, before the content is built: if building fails (an image that cannot be
        # downloaded) the messages are still here for the next rebuild to use.
        tin_chen_da_keo.extend(masked)
        return masked

    # ``lay_image_mode`` is a FUNCTION: ``image_mode`` changes mid-turn when the provider refuses pixels and
    # the loop rebuilds the input without images. Passing the value would build the injected message in a mode
    # that is no longer valid.
    chen_tin_giua_luot = tao_bo_chen_tin(
        lay_tin_chen=lay_tin_chen if cb.fetch_injected_messages is not None else None,
        lay_image_mode=lambda: image_mode,
        lay_tran_token=lambda: tran_token,
        guard=guard,
        deps=content_deps,
    )

    async def prepare_step(current: list[ModelMessage]) -> list[ModelMessage] | None:
        injected = await chen_tin_giua_luot(current)
        if progress.hand_off is not None:
            raise _MidTurnHandOff
        return injected

    def on_step_finish(step: RawStep) -> None:
        progress.steps += 1
        if step.usage is not None:
            progress.usage = progress.usage.plus(step.usage)
        quan_sat_step(step)

    async def gan_tin_chen_vao(goc: list[ModelMessage]) -> list[ModelMessage]:
        """Attach the injected messages to the context, built RIGHT BEFORE each model call.

        ``messages`` always holds the PURE version, never an injected message. A first version assigned back
        to ``messages`` in all 4 repair branches and caused two bugs at once:

        1. The attach is NOT idempotent. Two chained repair branches (context overflow then empty completion,
           both real cases of this router) put TWO identical copies of the injected message in the prompt; the
           model reads "this person repeated themselves", just when it is told not to redo finished work.
        2. Worse: the wrap-up takes the question as ``messages[-1]``. Assigning back makes the last element
        the
           INJECTED message, so the original question falls into the cut zone, reopening the very trap the
           wrap-up comment says was fixed.

        Goes through ``dung_tin_chen_trong_ngan_sach`` and not ``dung_tin_chen``: that is the ONLY door that
        applies the token ceiling and drops images when the injected message is too big. Bypassing it makes
        the context-overflow branch push 8 base64 image blocks back in, in the very turn the provider just
        refused for being too long.
        """
        if not tin_chen_da_keo:
            return goc
        return [
            *goc,
            await dung_tin_chen_trong_ngan_sach(tin_chen_da_keo, image_mode, tran_token, deps=content_deps),
        ]

    # System prompt + tools ALREADY SENT in the main call, captured to measure chars/token at the end of the
    # turn (the calibration path of ``KY_TU_MOI_TOKEN``, see ``token_estimate``).
    he_thong_da_gui = ""
    tool_set_da_gui: Mapping[str, AgentTool] | None = None

    def build_prompt() -> str:
        return build_system_prompt(
            agent,
            model_latest,
            memory,
            account,
            isolated,
            registry=deps.tools,
            channel=caps,
            identity_unverified=profile.require_identity_verification
            and not isolated
            and not ctx.identity_verified,
        )

    def thread_session() -> ThreadSession:
        return ThreadSession(account.id, latest.thread_id, context_epoch)

    def model_for_turn() -> ChatModel:
        return deps.resolve_model(agent, thread_session())

    async def run_once() -> StreamTextResult:
        nonlocal he_thong_da_gui, tool_set_da_gui
        # Build the input HERE and do not assign back into ``messages`` (see ``gan_tin_chen_vao``).
        # ``prepare_step`` only inserts the NEW part it pulled, while this one gathers ALL of
        # ``tin_chen_da_keo``, so the two paths never overlap.
        ngu_canh = await gan_tin_chen_vao(messages)
        he_thong = build_prompt()
        # Two filter layers intersect: the agent declares capability, the account applies policy; ``isolated``
        # drops the tools unfit for a scheduled turn (add_reaction has no real msg id, read_image has no
        # image, save_memory blocks injection from a job, a job must not create jobs).
        tool_set = await deps.tools.build_agent_tools(
            ToolContext(
                clinic_id=clinic_id,
                account=account,
                agent=agent,
                channel=channel,
                message=model_latest,
                batch=model_batch,
                policy=ctx,
                isolated=isolated,
                record_sent=cb.record_tool_sent,
            )
        )
        he_thong_da_gui = he_thong
        tool_set_da_gui = tool_set
        return await chay_stream(
            model=model_for_turn(),
            system=he_thong,
            messages=ngu_canh,
            tools=tool_set,
            # Two stop conditions plus the guard. ``step_count_is`` bounds the NUMBER of rounds; the token
            # condition bounds the SIZE: tool results accumulate through the steps (``web_fetch`` alone can
            # reach WEB_FETCH_MAX_CHARS), so a turn with few steps can still bloat. Measured on the real DB: a
            # turn accumulated 184,835 tokens over 8 steps. It uses the SAME discounted budget as the context
            # trimming, not the raw ceiling: against the raw ceiling this condition almost never ran, since
            # the provider answers 400 before the usage of that call is back, so the function was never called
            # with an exceeding number.
            stop_when=[
                step_count_is(tran_step),
                vuot_tran_token(ngan_sach_an_toan(tran_token)),
                # The guard decided to block: stop the loop. The last step still has tool calls, so
                # ``can_luot_chot`` catches it and the turn goes to the wrap-up call: the model must answer
                # with what it has gathered instead of leaving the user a progress narration.
                lambda _steps: guard.da_chan(),
            ],
            max_output_tokens=get_tuning_int("LLM_MAX_OUTPUT_TOKENS"),
            # Thinking on by LLM_REASONING_EFFORT: verify with usage.reasoning_tokens > 0 in the log below.
            provider_options=resolve_reasoning_options(agent),
            max_retries=2,
            # Upper bound for the WHOLE turn. Without it a router that accepts the connection and hangs would
            # eat the connection timeout x max_retries x steps and lock the thread for hours while later
            # messages queue behind it. Cancellation also reaches a running tool (``abortSignal``).
            timeout_s=get_tuning_int("LLM_TURN_TIMEOUT_MS") / 1000,
            headers=None,
            # Log every tool call with its input size and a short head of the output: when the bot answers
            # poorly one must see which page it fetched (no content in the log, see agent_step_observer).
            on_step_finish=on_step_finish,
            # Step boundary: after the tool results, BEFORE the next LLM call: the insertion point goclaw
            # uses. The overriding message list is carried to later steps, so inserting once is enough.
            prepare_step=prepare_step,
            sleep=deps.sleep,
            retry_initial_delay_s=deps.retry_initial_delay_s,
            on_attempt_error=_log_stream_error,
            tool_output_text_filter=masker.text,
        )

    async def run_wrap_up(da_lam: list[ModelMessage]) -> str:
        """The WRAP-UP call once the steps ran out: replay exactly what the model just did and ask again
        WITHOUT tools. No tools is the crux: with tools the model calls again and falls into the very trap it
        just left."""
        nhac_chot: ModelMessage = {"role": "user", "content": WRAP_UP_PROMPT}
        # The wrap-up MUST go through the budget. Otherwise the cure for "context about to overflow" is a call
        # BIGGER than the one that nearly overflowed: it sends ``messages`` AND all of ``da_lam`` (tool call +
        # tool result of every step) plus the reminder. Wrap up and get a 400, and the work of the whole turn
        # is lost.  The question is SEPARATED from the cut zone instead of relying on ``so_tin_bao_ve_cuoi``.
        # The earlier version passed ``[...messages, ...da_lam, nhac_chot]`` with a protected tail of 2 and
        # the comment "the current turn's message sits right before nhac_chot": WRONG by structure. The
        # question is the last of ``messages``, i.e. BEFORE ALL of ``da_lam``; the two protected messages were
        # really ``nhac_chot`` and one tool message of the last step. The cut drops from the START of the
        # array, so the order dropped is: history -> THE USER'S QUESTION -> the tool pairs.  Measured on a
        # heavy turn (20 history messages + 8 tool pairs with 100k-char results): cut to 5 messages and NO
        # question left. The model got "answer NOW" without knowing what was asked: exactly what the wrap-up
        # exists to avoid. This case only blows up on a heavy turn, i.e. right after burning 8 steps.
        cau_hoi = messages[-1] if messages else None
        truoc_cau_hoi = messages[:-1]

        # The injected messages go into the PROTECTED tail with the question and the reminder, NOT into the
        # cut part. It is the newest thing and often the one that CORRECTS the request; cutting it and then
        # telling the model "answer NOW" is wrapping up on an outdated request, and the wrap-up is what
        # produces the sentence sent out. A variant of the trap fixed once above: that time the QUESTION was
        # cut, this time the CORRECTION. Through the budget door like every other path that builds an injected
        # message: the wrap-up is where the context is tightest (it already carries all of ``da_lam``).
        tin_chen_chot = (
            [await dung_tin_chen_trong_ngan_sach(tin_chen_da_keo, image_mode, tran_token, deps=content_deps)]
            if tin_chen_da_keo
            else []
        )
        duoi_bao_ve = [*([cau_hoi] if cau_hoi is not None else []), *tin_chen_chot, nhac_chot]
        chua_cho_san = uoc_luong_token_tin_nhan(duoi_bao_ve, _tokens_per_image())

        cat = cat_ngu_canh_theo_ngan_sach(
            tin_nhan=[*truoc_cau_hoi, *da_lam],
            # Leave room for the tail that is never cut
            tran_token=max(0, ngan_sach_an_toan(tran_token) - chua_cho_san),
            so_tin_bao_ve_cuoi=1,
            co_anh=_image_quality(),
        )
        tin_chot = [*cat.tin_nhan, *duoi_bao_ve]
        if cat.da_cat is not None:
            log.warning("context trimmed for the wrap-up call", **dataclasses.asdict(cat.da_cat))

        # Streaming for the reason of ``run_once``, and here it matters even more: the wrap-up is always the
        # longest generation (the model writes the answer from everything gathered), so the likeliest to pass
        # the 100 s mark of the CDN.
        r = await chay_stream(
            model=model_for_turn(),
            system=build_prompt(),
            messages=tin_chot,
            max_output_tokens=get_tuning_int("LLM_MAX_OUTPUT_TOKENS"),
            max_retries=1,
            timeout_s=get_tuning_int("LLM_TURN_TIMEOUT_MS") / 1000,
            sleep=deps.sleep,
            retry_initial_delay_s=deps.retry_initial_delay_s,
            on_attempt_error=_log_stream_error,
        )
        if get_tuning_bool("AGENT_TRACE_ENABLED"):
            trace.append(
                summarize_step(
                    r.steps[0] if r.steps else RawStep(),
                    get_tuning_int("AGENT_TRACE_MAX_CHARS"),
                    lan_chay + 1,
                )
            )
        return r.text

    def is_glitch(r: StreamTextResult) -> bool:
        return is_empty_router_completion(
            text=r.text,
            tool_call_count=sum(len(s.tool_calls) for s in r.steps),
            total_tokens=r.total_usage.total_tokens or 0,
        )

    async def thu_lai_khong_pixel(err: BaseException) -> StreamTextResult:
        """Rebuild the input WITHOUT pixels and run again: the reactive fallback when the provider refuses a
        turn carrying images with a 4xx."""
        nonlocal messages, image_mode, lan_chay
        fallback_mode: ImageContextMode = "describe" if is_sidecar_configured() else "blind"
        log.warning(
            "provider refused a turn with images (4xx): retrying without pixels",
            image_mode=image_mode,
            fallback_mode=fallback_mode,
            err=err,
        )
        rebuilt = await build_turn_messages(
            history=history,
            batch=model_batch,
            override=agent,
            force_mode=fallback_mode,
            allowlist=account.allowlist,
            # This path once FORGOT to pass the ceiling, so the retry ran with no budget at all, exactly when
            # the context was heavy enough for the provider to have just refused it.
            tran_token=tran_token,
            deps=content_deps,
        )
        image_mode = rebuilt.image_mode
        # Re-attach AFTER ``image_mode`` changed: the injected message must be built in the NEW mode, or the
        # turn the provider refused over an image receives one more.
        messages = rebuilt.messages
        if rebuilt.da_cat is not None:
            log.warning(
                "context exceeded the budget on the rebuild: trimmed",
                tran_token=tran_token,
                **dataclasses.asdict(rebuilt.da_cat),
            )
        lan_chay += 1
        guard.dat_lai()
        return await run_once()

    async def chua_loi_provider(err: BaseException) -> StreamTextResult:
        """Repair by the EXACT kind of provider error. Each kind is retried AT MOST ONCE: the loop already has
        two tolerance layers (the ``max_retries`` of the model call, the empty-completion retry); stacking
        more
        multi-layer backoff is three layers overriding each other."""
        nonlocal messages, lan_chay
        loai = phan_loai_loi_provider(err)
        log.error("agent turn failed at the provider", kind=loai.value, http=ma_http_cua(err), err=err)

        if loai in (ProviderErrorKind.AUTH, ProviderErrorKind.CONFIG):
            # NO retry: a wrong key (or a configuration not entered yet) only gets three times slower and
            # still fails. Raise so the caller sends a sentence that says this is configuration, not a blip.
            raise err

        if loai is ProviderErrorKind.RATE_LIMIT:
            cho = giay_cho_lai(err)
            cho = 5.0 if cho is None else cho
            log.warning("provider is throttling: wait, then retry exactly once", wait_s=cho)
            await deps.sleep(cho)
            lan_chay += 1
            guard.dat_lai()
            return await run_once()

        if loai is ProviderErrorKind.CONTEXT_OVERFLOW:
            # Cut DEEPER than the first time (half the normal budget): the provider just said plainly it is
            # too long, so our estimate is more optimistic than reality.
            hep = cat_ngu_canh_theo_ngan_sach(
                tin_nhan=messages,
                tran_token=ngan_sach_an_toan(tran_token) // 2,
                so_tin_bao_ve_cuoi=1,
                co_anh=_image_quality(),
            )
            if hep.da_cat is not None:
                log.warning(
                    "provider reported context overflow: cutting deeper and retrying once",
                    **dataclasses.asdict(hep.da_cat),
                )
            # Attach the injected message AFTER cutting (``gan_tin_chen_vao`` in ``run_once``): it is the
            # newest and may be the one that CHANGES the request, so cutting it to keep the old history keeps
            # the wrong part. The builder already drops its images when it is too big, so it is not what
            # overflowed.
            messages = hep.tin_nhan
            lan_chay += 1
            guard.dat_lai()
            return await run_once()

        # transient + unknown: the ``max_retries`` of the model call already tried; trying more here would
        # only repeat the same thing. Raise so the caller tells the user.
        raise err

    result: StreamTextResult
    try:
        result = await run_once()
    except Exception as err:
        # Reactive fallback: the turn carries pixels and the provider refuses with a 4xx (an endpoint outside
        # the router declares no capability and the detection guessed optimistically) -> remember the model as
        # blind, rebuild without pixels and retry once. A combo through the router does not land here: the
        # router strips the image quietly, no error.
        if (
            image_mode not in ("native", "hybrid")
            or not has_image_parts(messages)
            or not is_image_rejection_error(err)
        ):
            # NOT an image error: classify and repair the right disease. This branch must come AFTER the image
            # one above: an image error is also a 400, and letting the classifier run first would answer
            # "unknown" and the pixel-dropping path would never run.
            result = await chua_loi_provider(err)
        else:
            mark_model_no_vision(agent)
            result = await thu_lai_khong_pixel(err)

    # The router sometimes answers 200 with an EMPTY completion (0 tokens). The ``max_retries`` of the model
    # call does not retry a "successful" response: retry ONCE here.
    if is_glitch(result):
        log.warning("router returned an empty completion (0 tokens): retrying once")
        lan_chay += 1
        guard.dat_lai()
        result = await run_once()

    lech = so_sanh_uoc_luong(
        uoc_luong_token_tin_nhan(messages, _tokens_per_image()),
        result.steps[0].usage.input_tokens if result.steps and result.steps[0].usage else None,
    )

    # info + tool names: when the bot answers poorly one must see at once what it ALREADY called; before this
    # there was only the step count and debugging was all guessing.
    log.info(
        "agent turn finished",
        batch_size=len(batch),
        # Messages the user sent mid-turn. Present because the estimate below is over ``messages`` (WITHOUT
        # the injected ones) while the real number has them: a turn with a nonzero value must be left out of
        # the calibration of the two estimator constants.
        so_tin_chen=len(tin_chen_da_keo),
        # native = the model reads images itself; describe = the sidecar describes; hybrid = a combo receives
        # pixels + description; blind = images dropped. After a reactive fallback this is the mode that REALLY
        # ran (describe/blind), not the initial one.
        image_mode=image_mode,
        steps=len(result.steps),
        finish_reason=result.finish_reason,
        # The model that REALLY answered (a router may route to another one silently)
        model=result.model_id,
        reasoning_effort=resolve_reasoning_effort(agent).value,
        # > 0 is solid proof the cache is hitting. 0 proves nothing: "upstream reported 0 hits" and "upstream
        # does not report the field" look identical to the client.
        cached_tokens=result.total_usage.cache_read_tokens or 0,
        tool_calls=[call.tool_name for step in result.steps for call in step.tool_calls],
        input_tokens=result.total_usage.input_tokens,
        output_tokens=result.total_usage.output_tokens,
        reasoning_tokens=result.total_usage.reasoning_tokens,
        # The estimate next to the REAL number, logged at EVERY turn and not only the trimmed ones: the
        # calibration path of the two constants of ``token_estimate`` (chars per token, tokens per image). It
        # cannot be measured from the usage table (its columns are the TOTAL over all steps). Compared with
        # the FIRST step, the only call whose input equals exactly system + tools + messages (a later step
        # adds the tool results). Calibrate with ``ky_tu_input / that``, NOT with ``lech_phan_tram``: the
        # latter compares the estimate over ``messages`` only with a ``that`` that covers system + tools too,
        # so it is low systematically (a quick read next to the real number, not a calibration denominator).
        ky_tu_input=dem_ky_tu_input_day_du(he_thong_da_gui, tool_set_da_gui, messages),
        uoc_luong=None if lech is None else dataclasses.asdict(lech),
    )

    # Still empty after the retry: answer with a fallback instead of silently leaving the sender hanging. A
    # turn that "only reacts" is valid and does not land here (it has a tool call and tokens).
    if is_glitch(result):
        log.error("router returned an empty completion twice in a row: answering with the fallback")
        return AgentTurnResult(
            text=ROUTER_DOWN_REPLY,
            usage=TokenUsage(steps=len(result.steps)),
            turn_id=turn_id,
        )

    # Step ceiling reached: the loop stopped because the TURNS ran out, not because the model finished, so
    # ``result.text`` is the text of the step that was calling tools. Since the persona teaches the model to
    # narrate progress, that text is a sentence like "Two sources, now cross-checking and answering."; sending
    # it straight out hands the user exactly that as the answer, and next turn the model reads in the history
    # that it answered that way. (Before that persona the text was empty and the bot stayed silent: also
    # broken.) The cure is ONE wrap-up call with NO tools: the model must write the answer from what it
    # gathered instead of throwing away the work of 8 steps.  Since ``stop_when`` also has the TOKEN
    # condition, a turn can stop early with ``steps < max_steps``, so the condition must be ``can_luot_chot``
    # (the last step still calls tools), not ``hit_step_limit`` (which also demands enough steps). Using the
    # old function would send the progress narration out of a turn that stopped for tokens.
    last_step_tool_calls = len(result.steps[-1].tool_calls) if result.steps else 0
    if can_luot_chot(last_step_tool_calls=last_step_tool_calls):
        # The label must name EXACTLY one of the THREE stop conditions. The first version had two so it wrote
        # "out of steps" : "hit the token ceiling" as a binary; the guard was added later and every guard
        # block was logged as the token ceiling: the very line one reads to understand why a turn was cut.
        het_step = hit_step_limit(
            step_count=len(result.steps), max_steps=tran_step, last_step_tool_calls=last_step_tool_calls
        )
        chan = guard.ly_do_chan()
        log.warning(
            "loop stopped while the model was still calling tools: running a wrap-up call without tools",
            steps=len(result.steps),
            max_steps=tran_step,
            ly_do=nhan_ly_do_dung(ma_guard_chan=chan.ma if chan is not None else None, het_step=het_step),
            # The guard's sentence kept as it is: it says which tool and how many times
            guard=chan.thong_diep if chan is not None else None,
        )
        try:
            chot: str | None = await run_wrap_up(result.response_messages)
        except Exception as err:
            log.error("the wrap-up call failed too", err=err)
            chot = None
        text = await deps.policy.after_llm(ctx, (chot or "").strip() or STEP_LIMIT_REPLY, mask_token)
        return AgentTurnResult(
            text=text, usage=_usage_of(result.total_usage, len(result.steps)), turn_id=turn_id
        )

    text = await deps.policy.after_llm(ctx, result.text.strip(), mask_token)
    return AgentTurnResult(text=text, usage=_usage_of(result.total_usage, len(result.steps)), turn_id=turn_id)


class DefaultAgentEngine:
    """``pema_contracts.agent_turn.AgentEngine``: what the channel turn processor and the scheduler inject."""

    def __init__(self, deps: AgentEngineDeps) -> None:
        self._deps = deps

    async def run_turn(
        self, request: AgentTurnRequest, callbacks: TurnCallbacks | None = None
    ) -> AgentTurnResult:
        return await run_agent_turn(self._deps, request, callbacks)
