"""``agent chat``: talk to an agent from the terminal."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Final
from uuid import uuid4

from agent_app.model_factory import build_model, describe_model
from agent_app.profile import Profile, load_profile
from agentcore import (
    DEFAULT_TENANT,
    ContextManager,
    InMemorySessionStore,
    LlmRequest,
    ModelError,
    PromptBuilder,
    PromptEnv,
    SessionStore,
    StepInfo,
    TokenEstimator,
    ToolRegistry,
    ToolResultBlock,
    ToolUseBlock,
    TurnInfo,
    TurnResult,
    builtin_sections,
    run_turn,
)
from agentcore.clock import utc_now
from agentcore.harness.tools.builtin import builtin_tools

EXIT_CONFIG_ERROR: Final = 2
PREVIEW_CHARS: Final = 120
CHANNEL: Final = "cli"
HELP: Final = (
    "Commands: /new (start a new session), /prompt (show what the model gets), "
    "/context (context size), /compact (summarise older turns now), /exit (quit), /help (this help)\n"
)


def main(argv: Sequence[str] | None = None) -> int:
    _use_utf8_text_streams()
    parser = argparse.ArgumentParser(prog="agent", description="General-purpose agent")
    commands = parser.add_subparsers(dest="command", required=True)
    chat = commands.add_parser("chat", help="Chat with an agent in the terminal")
    chat.add_argument("--profile", type=Path, required=True, help="path to a TOML profile")
    chat.add_argument("--fake", action="store_true", help="use an echo model: no provider, no API key")
    chat.add_argument("--session", default=None, help="session id (default: a new random one)")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_chat(args.profile, fake=args.fake, session=args.session))
    except KeyboardInterrupt:
        _write("\n")
        return 0


async def _chat(profile_path: Path, *, fake: bool, session: str | None) -> int:
    try:
        profile = load_profile(profile_path)
        tools = builtin_tools(timezone=profile.agent.timezone).subset(profile.agent.tools)
        prompt = build_prompt(profile, tool_names=tools.names())
        model = build_model(profile, fake=fake, env=os.environ)
        context_policy = profile.context_policy()
    except (OSError, ValueError, ModelError) as err:
        _write(f"error: {err}\n")
        return EXIT_CONFIG_ERROR

    context = ContextManager(context_policy, model) if context_policy else None
    store = InMemorySessionStore()
    session_id = session or _new_session_id()
    lines = _stdin_lines()
    model_label = describe_model(profile, fake=fake, env=os.environ)
    _write(f"agent '{profile.agent.name}' | model: {model_label} | session: {session_id}\n{HELP}")

    while True:
        _write("you> ")
        line = await lines.get()
        if line is None:
            _write("\n")
            return 0
        text = line.strip()
        if not text:
            continue
        if text in {"/exit", "/quit"}:
            return 0
        if text == "/help":
            _write(HELP)
            continue
        if text == "/new":
            session_id = _new_session_id()
            _write(f"new session: {session_id}\n")
            continue
        if text == "/prompt":
            _write(await show_prompt(prompt, store, session_id, max_steps=profile.loop.max_steps))
            continue
        if text == "/context":
            output_tokens = profile.loop.max_output_tokens
            _write(
                await show_context(prompt, store, session_id, tools, context, max_output_tokens=output_tokens)
            )
            continue
        if text == "/compact":
            output_tokens = profile.loop.max_output_tokens
            try:
                _write(await compact_now(prompt, store, session_id, context, max_output_tokens=output_tokens))
            except ModelError as err:
                _write(f"error ({err.kind}): {err}\n")
            continue
        try:
            result = await run_turn(
                session_id=session_id,
                user_text=text,
                prompt=prompt,
                model=model,
                tools=tools,
                store=store,
                policy=profile.loop_policy(),
                channel=CHANNEL,
                context=context,
            )
        except ModelError as err:
            _write(f"error ({err.kind}): {err}\n")
            continue
        _write(render_turn(result))


def build_prompt(profile: Profile, *, tool_names: Sequence[str]) -> PromptBuilder:
    env = PromptEnv(
        agent_name=profile.agent.name,
        persona=profile.agent.system_prompt,
        timezone=profile.agent.timezone,
        tool_names=tuple(tool_names),
    )
    return PromptBuilder(env, builtin_sections().select(profile.prompt.sections))


async def show_prompt(prompt: PromptBuilder, store: SessionStore, session_id: str, *, max_steps: int) -> str:
    """The session's system prompt (frozen on first use) and the context block the next message would get."""
    system = await prompt.system(store, DEFAULT_TENANT, session_id)
    turn = prompt.start_turn(TurnInfo(now=utc_now(), channel=CHANNEL))
    context = turn.context(StepInfo(step=1, max_steps=max_steps))
    return (
        f"--- system prompt (frozen for this session) ---\n{system}\n"
        f"--- context block for the next message ---\n{context or '(none)'}\n"
    )


async def show_context(
    prompt: PromptBuilder,
    store: SessionStore,
    session_id: str,
    tools: ToolRegistry,
    context: ContextManager | None,
    *,
    max_output_tokens: int,
) -> str:
    """Roughly how big the next request is (system prompt, visible history, tools) against the budget."""
    history = await store.load(DEFAULT_TENANT, session_id)
    compaction = await store.load_compaction(DEFAULT_TENANT, session_id)
    first_kept = compaction.first_kept if compaction else 0
    request = LlmRequest(
        system=await prompt.system(store, DEFAULT_TENANT, session_id),
        messages=history[first_kept:],
        tools=tools.schemas(),
        max_output_tokens=max_output_tokens,
    )
    estimator = context.estimator if context else TokenEstimator()
    lines = [f"context: ~{estimator.request(request)} tokens, {len(history) - first_kept} messages sent"]
    if context is None:
        lines.append("compaction: off (no [context] window_tokens in the profile)")
    else:
        policy = context.policy
        lines.append(
            f"compaction at ~{policy.threshold(max_output_tokens)} tokens "
            f"(window {policy.window_tokens}, keeps ~{policy.keep_budget(max_output_tokens)} recent)"
        )
    if compaction is not None:
        lines.append(
            f"summary: {len(compaction.summary)} chars for the first {first_kept} of {len(history)} messages"
        )
    return "\n".join(lines) + "\n"


async def compact_now(
    prompt: PromptBuilder,
    store: SessionStore,
    session_id: str,
    context: ContextManager | None,
    *,
    max_output_tokens: int,
) -> str:
    if context is None:
        return "compaction is off: set [context] window_tokens in the profile\n"
    history = await store.load(DEFAULT_TENANT, session_id)
    outcome = await context.compact(
        store=store,
        tenant_id=DEFAULT_TENANT,
        session_id=session_id,
        keep_from=len(history),
        max_output_tokens=max_output_tokens,
        force=True,
    )
    if outcome is None:
        return "nothing to compact yet\n"
    await prompt.system(store, DEFAULT_TENANT, session_id, refresh=True)
    note = " (no summary: the summariser failed)" if outcome.fallback else ""
    return f"compacted {outcome.compacted_messages} messages{note}\n"


def render_turn(result: TurnResult) -> str:
    lines: list[str] = []
    for message in result.new_messages:
        for block in message.blocks:
            if isinstance(block, ToolUseBlock):
                shown = (
                    block.raw_args
                    if block.raw_args is not None
                    else json.dumps(block.args, ensure_ascii=False)
                )
                lines.append(f"  [tool] {block.name}({_preview(shown)})")
            elif isinstance(block, ToolResultBlock):
                status = "error" if block.is_error else "ok"
                lines.append(f"  [tool] {block.name} -> {status}: {_preview(block.content)}")
    lines.append(f"agent> {result.text}")
    usage = result.usage
    compacted = f", compactions={result.compactions}" if result.compactions else ""
    lines.append(
        f"  (steps={result.steps}, in={usage.input_tokens}, out={usage.output_tokens}, "
        f"stop={result.stop}{compacted})"
    )
    return "\n".join(lines) + "\n"


def _stdin_lines() -> asyncio.Queue[str | None]:
    """Reads stdin on a daemon thread, so Ctrl+C and the end of the program never wait for a pending read.
    ``None`` marks the end of input."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def push(item: str | None) -> bool:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:  # the event loop is closed: the chat has ended
            return False
        return True

    def read() -> None:
        for line in sys.stdin:
            if not push(line):
                return
        push(None)

    threading.Thread(target=read, name="agent-stdin", daemon=True).start()
    return queue


def _new_session_id() -> str:
    return f"cli-{uuid4().hex[:8]}"


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= PREVIEW_CHARS else flat[:PREVIEW_CHARS] + "..."


def _use_utf8_text_streams() -> None:
    """On Windows a pipe or a file falls back to the legacy code page and garbles Vietnamese text; a console
    already speaks UTF-8. Undecodable or unencodable characters are replaced instead of crashing the chat."""
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        if _is_terminal(stream):
            reconfigure(errors="replace")
        else:
            reconfigure(encoding="utf-8", errors="replace")


def _is_terminal(stream: object) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
