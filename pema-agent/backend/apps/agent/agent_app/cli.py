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

from agent_app.assembly import Agent, build_agent
from agent_app.model_factory import describe_model
from agent_app.profile import load_profile
from agent_app.storage import AgentDatabase, PostgresMemoryBackend, PostgresSkillStore
from agentcore import (
    DEFAULT_TENANT,
    ContextManager,
    InMemorySessionStore,
    LlmRequest,
    Message,
    ModelError,
    PromptBuilder,
    SessionStore,
    StepInfo,
    TokenEstimator,
    ToolContext,
    ToolRegistry,
    ToolResultBlock,
    ToolUseBlock,
    TurnInfo,
    TurnResult,
    Usage,
    run_turn,
)
from agentcore.clock import utc_now
from agentcore.loop.run_turn import flush_memory
from agentcore.memory import MemoryService

EXIT_CONFIG_ERROR: Final = 2
PREVIEW_CHARS: Final = 120
CHANNEL: Final = "cli"
CLI_USER: Final = "cli-user"
DATABASE_URL_ENV: Final = "AGENT_DATABASE_URL"
HELP: Final = (
    "Commands: /new (start a new session), /prompt (show what the model gets), /context (context size), "
    "/compact (summarise older turns now), /memory (saved notes), /exit (quit), /help (this help)\n"
)


def main(argv: Sequence[str] | None = None) -> int:
    _use_utf8_text_streams()
    parser = argparse.ArgumentParser(prog="agent", description="General-purpose agent")
    commands = parser.add_subparsers(dest="command", required=True)
    chat = commands.add_parser("chat", help="Chat with an agent in the terminal")
    chat.add_argument(
        "--profile", type=Path, required=True, help="agent folder (with agent.toml) or a TOML profile"
    )
    chat.add_argument("--fake", action="store_true", help="use an echo model: no provider, no API key")
    chat.add_argument("--session", default=None, help="session id (default: a new random one)")
    args = parser.parse_args(argv)
    # psycopg's async driver cannot run on the Windows proactor loop.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        return asyncio.run(
            _chat(args.profile, fake=args.fake, session=args.session), loop_factory=loop_factory
        )
    except KeyboardInterrupt:
        _write("\n")
        return 0


async def _chat(profile_path: Path, *, fake: bool, session: str | None) -> int:
    db_url = os.environ.get(DATABASE_URL_ENV)
    db = AgentDatabase(db_url) if db_url else None
    try:
        return await _chat_with(profile_path, fake=fake, session=session, db=db)
    finally:
        if db is not None:
            await db.dispose()


async def _chat_with(profile_path: Path, *, fake: bool, session: str | None, db: AgentDatabase | None) -> int:
    try:
        profile = load_profile(profile_path)
        agent = build_agent(
            profile,
            fake=fake,
            env=os.environ,
            memory_backend=PostgresMemoryBackend(db) if db else None,
            skill_store=PostgresSkillStore(db) if db else None,
        )
    except (OSError, ValueError, ModelError) as err:
        _write(f"error: {err}\n")
        return EXIT_CONFIG_ERROR

    store = InMemorySessionStore()
    session_id = session or _new_session_id()
    lines = _stdin_lines()
    model_label = describe_model(profile, fake=fake, env=os.environ)
    storage = "postgres" if db else f"in process memory (set {DATABASE_URL_ENV} to keep notes and skills)"
    _write(
        f"agent '{profile.agent.name}' | model: {model_label} | session: {session_id}\n"
        f"notes and skills: {storage}\n{HELP}"
    )

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
        if text.startswith("/"):
            await _command(text, agent, store, session_id)
            continue
        try:
            observer = ConsoleObserver()
            result = await run_turn(
                session_id=session_id,
                user_text=text,
                prompt=agent.prompt,
                model=agent.model,
                tools=agent.tools,
                store=store,
                policy=agent.policy,
                user_id=CLI_USER,
                channel=CHANNEL,
                context=agent.context,
                observer=observer,
            )
        except ModelError as err:
            _write(f"\nerror ({err.kind}): {err}\n")
            continue
        _write(observer.finish(result))


async def _command(text: str, agent: Agent, store: SessionStore, session_id: str) -> None:
    loop = agent.profile.loop
    try:
        if text == "/prompt":
            _write(await show_prompt(agent.prompt, store, session_id, max_steps=loop.max_steps))
        elif text == "/context":
            _write(
                await show_context(
                    agent.prompt,
                    store,
                    session_id,
                    agent.tools,
                    agent.context,
                    max_output_tokens=loop.max_output_tokens,
                )
            )
        elif text == "/compact":
            _write(await compact_now(agent, store, session_id))
        elif text == "/memory":
            _write(await show_memory(agent.memory, agent=agent.profile.agent.name))
        else:
            _write(f"unknown command: {text}\n{HELP}")
    except ModelError as err:
        _write(f"error ({err.kind}): {err}\n")


async def show_prompt(prompt: PromptBuilder, store: SessionStore, session_id: str, *, max_steps: int) -> str:
    """The session's system prompt (frozen on first use) and the context block the next message would get."""
    system = await prompt.system(store, DEFAULT_TENANT, session_id, user_id=CLI_USER)
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
        system=await prompt.system(store, DEFAULT_TENANT, session_id, user_id=CLI_USER),
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


async def compact_now(agent: Agent, store: SessionStore, session_id: str) -> str:
    """Summarise everything but the newest turn, after the same memory flush a turn would do."""
    if agent.context is None:
        return "compaction is off: set [context] window_tokens in the profile\n"
    history = await store.load(DEFAULT_TENANT, session_id)
    system = await agent.prompt.system(store, DEFAULT_TENANT, session_id, user_id=CLI_USER)
    max_output_tokens = agent.profile.loop.max_output_tokens

    async def flush(messages: Sequence[Message]) -> Usage:
        ctx = ToolContext(session_id=session_id, tenant_id=DEFAULT_TENANT, user_id=CLI_USER)
        return await flush_memory(
            model=agent.model,
            tools=agent.tools,
            ctx=ctx,
            system=system,
            messages=messages,
            max_output_tokens=max_output_tokens,
        )

    outcome = await agent.context.compact(
        store=store,
        tenant_id=DEFAULT_TENANT,
        session_id=session_id,
        keep_from=len(history),
        max_output_tokens=max_output_tokens,
        force=True,
        before_summary=flush,
    )
    if outcome is None:
        return "nothing to compact yet\n"
    await agent.prompt.system(store, DEFAULT_TENANT, session_id, user_id=CLI_USER, refresh=True)
    note = " (no summary: the summariser failed)" if outcome.fallback else ""
    return f"compacted {outcome.compacted_messages} messages{note}\n"


async def show_memory(memory: MemoryService | None, *, agent: str) -> str:
    if memory is None:
        return "memory is off: set [memory] enabled = true in the profile\n"
    snapshot = await memory.snapshot(DEFAULT_TENANT, agent, CLI_USER)
    lines = [f"agent notes ({len(snapshot.agent_notes)}):"]
    lines.extend(f"  - {note}" for note in snapshot.agent_notes)
    lines.append(f"notes about {CLI_USER} ({len(snapshot.user_notes)}):")
    lines.extend(f"  - {note}" for note in snapshot.user_notes)
    return "\n".join(lines) + "\n"


class ConsoleObserver:
    """Prints a turn while it runs: the reply as it streams, a note while the model thinks, tool calls."""

    def __init__(self) -> None:
        self._mid_line = False
        self._replying = False
        self._thinking = False
        self._streamed = False

    def text(self, delta: str) -> None:
        if not self._replying:
            self._end_line()
            _write("agent> ")
            self._replying = True
        _write(delta)
        self._mid_line = not delta.endswith("\n")
        self._streamed = True

    def thinking(self, delta: str) -> None:
        if not self._thinking and not self._replying:
            self._end_line()
            _write("  (thinking...)\n")
            self._thinking = True

    def tool_call(self, use: ToolUseBlock) -> None:
        self._end_line()
        shown = use.raw_args if use.raw_args is not None else json.dumps(use.args, ensure_ascii=False)
        _write(f"  [tool] {use.name}({_preview(shown)})\n")
        self._replying = self._thinking = False

    def tool_result(self, result: ToolResultBlock) -> None:
        status = "error" if result.is_error else "ok"
        _write(f"  [tool] {result.name} -> {status}: {_preview(result.content)}\n")

    def finish(self, result: TurnResult) -> str:
        """What is left to print once the turn is over: the reply if nothing streamed, and the stats."""
        head = "\n" if self._mid_line else ""
        if not self._streamed:
            head += f"agent> {result.text}\n"
        return head + stats_line(result) + "\n"

    def _end_line(self) -> None:
        if self._mid_line:
            _write("\n")
            self._mid_line = False


def stats_line(result: TurnResult) -> str:
    usage = result.usage
    parts = [
        f"steps={result.steps}",
        f"{result.duration_s:.1f}s",
        f"in={usage.input_tokens}",
        f"out={usage.output_tokens}",
    ]
    if usage.cache_read_tokens:
        parts.append(f"cached={usage.cache_read_tokens}")
    if usage.reasoning_tokens:
        parts.append(f"reasoning={usage.reasoning_tokens}")
    parts.append(f"stop={result.stop}")
    if result.compactions:
        parts.append(f"compactions={result.compactions}")
    return f"  ({', '.join(parts)})"


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
