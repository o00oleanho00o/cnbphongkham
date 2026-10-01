# ported from: evals/run-eval.ts
"""``python -m evals.run_eval`` (from ``pema-agent/backend``): run the case set against a REAL model.

It differs from ``pytest`` in purpose, not in degree: the tests run a fake model and so measure what is
deterministic (wiring, error branches, order). A fake model returns exactly what it was programmed to, so it
says NOTHING about whether a real model looks things up instead of guessing, or gets worse after the persona
is edited.

Three vital constraints, each patching one way the suite could betray itself:

1. NEVER touch a real channel. The engine hands the ``action`` tools a channel to send through; running with a
   real one means the bot messages real people. The runner builds its OWN fake channel and fake Zalo API, it
   does not accept one from outside.
2. TEMPORARY state. The settings are in memory and every case gets a fresh fake conversation store (the
   original's ``DELETE FROM memories`` between cases is "a new store per case" here), so the real DB is never
   written. The REAL DB is only READ, for the LLM and search settings (``read_real_*``).
3. Assertions on BEHAVIOUR (which tool was called) and STRUCTURAL properties, not on wording. Wording varies
   between runs, and a randomly red eval is one people stop reading, which loses the real reds too.

Forced deviations from the original, all consequences of what is and is not on this branch:

* The original went through ``processBatch`` (the production message processor, with the output-cleaning layer
  and the send path). That is the channel packages' (C1/C2), so the runner goes through ``run_agent_turn``
  (the engine, D1) and sends the reply through ``EvalWiring.format_reply`` into the fake Zalo API. Without a
  ``format_reply`` the runner has no styles to show: the cases that assert formatting then FAIL with "the
  runner did not provide it" (``cham_case``), never skip silently. Wire C2's markdown-to-styles translation
  there to measure formatting.
* The original used the production tool set; this branch builds it from ``FakeToolRegistry`` with canned
  synthetic web results (``eval_canned_tools``). Pass D4's registry as ``EvalWiring.registry`` to use the real
  tool bodies; ``search_probe`` then re-enables the web-search precondition check.
* The system sentences the original read from ``send-reply-in-parts`` (``TECHNICAL_ERROR_REPLY``,
  ``LOI_THEO_LOAI``) are not needed: the engine raises ``AgentTurnError`` for every failure, and the sentence
  it falls back to (``STEP_LIMIT_REPLY``, ``ROUTER_DOWN_REPLY``) is still compared.
* ``process.exit`` becomes a return code; ``console.log`` becomes a ``write`` callable.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from evals.eval_assert import QuanSat, ToolDaGoi, cham_case, phat_hien_luot_hong
from evals.eval_canned_tools import CANNED_RESULTS
from evals.eval_case_type import EvalCase
from evals.eval_cases import EVAL_CASES
from evals.eval_env import dung_eval_env
from evals.eval_formatting_view import SentMessage, dung_goc_nhin_dinh_dang
from evals.eval_report import KetQuaCase, in_bang
from evals.fake_zalo_api import FakeZaloApi, tao_fake_zalo_api
from evals.preflight_web_search import can_tra_cuu_web, kiem_tra_tien_de_tra_cuu
from pema.agent.agent_loop import ROUTER_DOWN_REPLY, STEP_LIMIT_REPLY, ModelResolver, run_agent_turn
from pema.agent.llm_provider import resolve_language_model
from pema.agent.streaming_model_test_helper import ScriptedModel
from pema.agent.testing import FakeToolRegistry
from pema.agent.testing_conversation import FakeConversation
from pema.agent.testing_engine import EngineHarness, fake_account, tin_nhan
from pema_contracts.agent_turn import AgentTurnRequest, TurnCallbacks
from pema_contracts.channel import ThreadKind
from pema_contracts.conversation import MemoryContextItem
from pema_contracts.testing import FAKE_CLINIC_ID, fake_agent_profile
from pema_contracts.tools import ToolRegistry
from pema_contracts.turn_errors import AgentTurnError

ACC = "eval-acc"
AGENT = "eval-agent"
EVAL_USER = "eval-user"

ReplyFormatter = Callable[[str], list[SentMessage]]
"""Splits and formats the reply text the way the channel would (messages + style ranges)."""

Write = Callable[[str], None]


def _stdout(line: str) -> None:
    sys.stdout.write(line + "\n")


@dataclass
class EvalWiring:
    """The seams of the runner. The defaults are the real model and the canned tool set."""

    resolve_model: ModelResolver | None = None
    """None = the REAL model of the effective LLM settings; tests pass a fake."""
    registry: Callable[[], ToolRegistry] | None = None
    """None = ``FakeToolRegistry`` with canned synthetic web results."""
    format_reply: ReplyFormatter | None = None
    """None = no style information (formatting cases fail honestly, see the module docstring)."""
    search_probe: Callable[[str], Awaitable[int]] | None = None
    """Number of results of a real search; enables the web-search precondition check."""
    search_provider_name: str = "unknown"
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    retry_initial_delay_s: float = 2.0
    cau_loi_he_thong: list[str] = field(default_factory=lambda: [ROUTER_DOWN_REPLY, STEP_LIMIT_REPLY])


@dataclass
class RunOutcome:
    ket_qua: list[KetQuaCase] = field(default_factory=list[KetQuaCase])
    tong_loi_goi_api: int = 0
    """Total calls through the fake API: PROOF all went through it, nothing reached a real channel."""


def _default_registry() -> ToolRegistry:
    return FakeToolRegistry(result_overrides=CANNED_RESULTS)


async def run_one_case(c: EvalCase, wiring: EvalWiring) -> tuple[KetQuaCase, FakeZaloApi]:
    thread_id = f"t-{c.ten}"
    thread_kind = ThreadKind.GROUP if c.la_nhom else ThreadKind.USER

    # A fresh store per case: this case must not see the fact the previous one just wrote (the original's
    # shared temp DB needed an explicit ``DELETE FROM memories``)
    conversation = FakeConversation()
    # Seed what the bot "already remembered": without a wrong fact the correction branch of ``save_memory``
    # means nothing
    conversation.memories = [MemoryContextItem(subject_id=EVAL_USER, content=f) for f in c.fact_co_san]
    # Seed ready-made HISTORY. A blank thread is NOT the real bot's context: a model imitates the formatting
    # of its own previous turn very strongly, so a case that measures the staying power of a rule against old
    # history must build that history.
    for tin in c.lich_su_truoc:
        conversation.add_message(ACC, thread_id, role=tin.role, content=tin.content)

    registry = wiring.registry() if wiring.registry is not None else _default_registry()
    agent = fake_agent_profile(
        id=AGENT,
        name="Agent eval",
        persona=c.persona,
        disabled_tools=list(c.disabled_tools),
        is_default=True,
    )
    harness = EngineHarness(
        conversation=conversation,
        account=fake_account(id=ACC, agent_id=AGENT),
        agent=agent,
    )
    # The REAL path records the incoming message in history the moment it arrives, then queues it. This runner
    # calls the engine directly, so it must do that step itself: without it the ``user`` row NEVER enters
    # history, the eval measures a history shape that does not exist in production, and no case goes through
    # the ``history_row_id`` filter.
    row_id = conversation.add_message(
        ACC, thread_id, role="user", content=c.tin_nhan, sender_name="Người dùng eval", sender_id=EVAL_USER
    )
    message = tin_nhan(
        c.tin_nhan,
        thread_id=thread_id,
        thread_kind=thread_kind,
        is_group=c.la_nhom,
        sender_id=EVAL_USER,
        sender_name="Người dùng eval",
        msg_id=f"m-{c.ten}",
        cli_msg_id=f"c-{c.ten}",
        mentions_me=True,
        history_row_id=row_id,
        update_id=f"u-{c.ten}",
    )

    deps = harness.deps(ScriptedModel([]))  # placeholder: its resolver is replaced right below
    deps.tools = registry
    deps.sleep = wiring.sleep
    deps.retry_initial_delay_s = wiring.retry_initial_delay_s
    # No injected resolver = the REAL model of the effective LLM settings
    deps.resolve_model = wiring.resolve_model if wiring.resolve_model is not None else resolve_language_model

    fake = tao_fake_zalo_api()
    callbacks = TurnCallbacks()
    request = AgentTurnRequest(clinic_id=FAKE_CLINIC_ID, account_id=ACC, batch=[message], isolated=False)

    started = time.monotonic()
    loi_chay: str | None = None
    tokens = 0
    text = ""
    try:
        result = await run_agent_turn(deps, request, callbacks)
        tokens = result.usage.total_tokens
        text = result.text
    except AgentTurnError as err:
        loi_chay = f"{err.kind.value}: {err.safe_message}"
    except Exception as err:
        # Anything else is a bug of the runner or the engine contract, still reported as a failed turn
        loi_chay = type(err).__name__
    giay = time.monotonic() - started

    if text:
        parts = wiring.format_reply(text) if wiring.format_reply is not None else [SentMessage(msg=text)]
        for part in parts:
            await fake.send_message(part.msg, thread_id, int(c.la_nhom), part.styles)

    steps = callbacks.trace
    kem_args = [
        ToolDaGoi(name=str(call.get("name", "?")), input=str(call.get("input", "")))
        for step in steps
        for call in step.tool_calls
    ]
    tool_da_goi = [t.name for t in kem_args]
    tra_loi = "\n".join(fake.tin_da_gui)

    # The engine RAISES for a failed turn, but a turn can still end in a system fallback sentence or in 0
    # tokens, and a case would be green exactly when the system is dead (see ``phat_hien_luot_hong``)
    hong = loi_chay or phat_hien_luot_hong(
        tokens=tokens,
        tra_loi=tra_loi,
        # STEP_LIMIT_REPLY is what the bot answers when the loop is cut AND the wrap-up call died too: without
        # it a case that only checks formatting would PASS on a turn that failed entirely and spent real money
        # (tokens > 0, so the second clause does not catch it either)
        cau_loi_he_thong=wiring.cau_loi_he_thong,
    )

    cham = cham_case(
        c,
        QuanSat(
            tool_da_goi=tool_da_goi,
            tool_da_goi_kem_args=kem_args,
            tra_loi=tra_loi,
            # The formatting that REALLY reached Zalo. ``tra_loi`` is the bare text after translation so it
            # cannot measure bold: see ``eval_formatting_view``. None when no formatter was wired.
            dinh_dang=dung_goc_nhin_dinh_dang(fake.tin_kem_dinh_dang) if wiring.format_reply else None,
            loi_chay=hong,
        ),
    )
    return (
        KetQuaCase(
            ten=c.ten,
            dat=cham.dat,
            ly_do_hong=cham.ly_do_hong,
            tool_da_goi=tool_da_goi,
            tokens=tokens,
            giay=giay,
            tra_loi=tra_loi,
        ),
        fake,
    )


async def run_cases(cases: list[EvalCase], wiring: EvalWiring, write: Write = _stdout) -> RunOutcome:
    out = RunOutcome()
    # SEQUENTIAL, not parallel: parallel both hits the router's rate limit and makes the table hard to read
    # when a case is red
    for c in cases:
        ket_qua, fake = await run_one_case(c, wiring)
        out.ket_qua.append(ket_qua)
        out.tong_loi_goi_api += len(fake.loi_goi)
        write(f"Đang chạy {c.ten}... {'ĐẠT' if ket_qua.dat else 'HỎNG'}")
    return out


def select_cases(only: str, cases: list[EvalCase]) -> list[EvalCase]:
    """``EVAL_ONLY=a,b``: a subset. Every turn is real tokens, so running the whole set while fixing one case
    or trying a hypothesis is waste."""
    chi_chay = [s.strip() for s in only.split(",") if s.strip()]
    return [c for c in cases if c.ten in chi_chay] if chi_chay else cases


async def main(wiring: EvalWiring | None = None, write: Write = _stdout) -> int:
    wiring = wiring or EvalWiring()
    chi_chay = os.environ.get("EVAL_ONLY", "")
    danh_sach = select_cases(chi_chay, EVAL_CASES)

    if not danh_sach:
        write(f'\nEVAL_ONLY="{chi_chay}" không khớp case nào.')
        write(f"Có: {', '.join(c.ten for c in EVAL_CASES)}\n")
        return 1

    restore: Callable[[], None] | None = None
    if wiring.resolve_model is None:
        env = await dung_eval_env()
        if not env.ok or env.llm is None or env.tra_cuu is None:
            write(f"\n{env.loi}\n")
            return 1
        restore = env.restore
        # Print the SOURCE of the configuration: reading the wrong source is measuring the wrong system, and
        # the model name alone does not say whether it came from the dashboard or the environment
        nguon = f"dashboard: {', '.join(env.llm.tu_db)}" if env.llm.tu_db else "chỉ môi trường"
        write(f"Model: {env.llm.model} ({env.llm.provider}) - nguồn {nguon}")
        tra_cuu = env.tra_cuu
        write(
            "Tra cứu: "
            + (
                f"{tra_cuu.provider} - nguồn dashboard: {', '.join(tra_cuu.tu_db)}"
                if tra_cuu.tu_db
                else "tool mẫu của eval (dữ liệu giả lập)"
            )
        )

    loc = f" (lọc từ {len(EVAL_CASES)})" if chi_chay else ""
    write(f"Số case: {len(danh_sach)}{loc}\n")

    try:
        # Precondition: web search must be alive, otherwise the result table lies
        if wiring.search_probe is not None and any(can_tra_cuu_web(c) for c in danh_sach):
            tien_de = await kiem_tra_tien_de_tra_cuu(wiring.search_probe, wiring.search_provider_name)
            if not tien_de.ok:
                write(f"\n{tien_de.loi}\n")
                return 1

        outcome = await run_cases(danh_sach, wiring, write)
    finally:
        if restore is not None:
            restore()

    in_bang(outcome.ket_qua, write)
    # Proof of constraint 1. The number comes from the FAKE API, so it says both "this many Zalo calls" and
    # "all of them were stopped here"
    write(f"\n{outcome.tong_loi_goi_api} lời gọi Zalo, tất cả vào API giả - không tin nào ra Zalo thật.")
    return 1 if any(not r.dat for r in outcome.ket_qua) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
