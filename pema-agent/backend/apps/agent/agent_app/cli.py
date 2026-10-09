"""``agent chat`` (chat in the terminal), ``agent serve`` (the HTTP gateway), ``agent model`` (stored model
settings), ``agent plugins`` and ``agent db``."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
import threading
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final, get_args
from uuid import uuid4

import psycopg
import uvicorn

from agent_app.assembly import Agent
from agent_app.db_roles import MIGRATION_URL_ENV, PASSWORD_ENV, RUNTIME_ROLE, bootstrap_role
from agent_app.gateway import ADMIN_TOKEN_ENV, TOKEN_ENV, GatewaySettings, create_app
from agent_app.ingress import SessionBusyError
from agent_app.model_factory import Provider, describe_model
from agent_app.model_settings import (
    SECRET_KEY_ENV,
    SETTING_FIELDS,
    ModelAdmin,
    PostgresModelSettingsStore,
    SecretKeyMissingError,
)
from agent_app.plugins import PluginError, PluginHost, discover
from agent_app.profile import Profile, load_profile
from agent_app.runtime import Runtime, build_runtime, plugin_roots, start_plugins
from agent_app.storage import AgentDatabase, PostgresSessionStore, SessionOwnerError
from agentcore import (
    DEFAULT_TENANT,
    ContextManager,
    LlmRequest,
    Message,
    ModelError,
    PromptBuilder,
    ReasoningEffort,
    SessionStore,
    StepInfo,
    TokenEstimator,
    ToolContext,
    ToolRegistry,
    ToolResultBlock,
    ToolUseBlock,
    TurnInfo,
    TurnResult,
    TurnTrace,
    Usage,
    run_turn,
)
from agentcore.clock import utc_now
from agentcore.harness.model.reasoning import OpenAIDialect
from agentcore.loop.run_turn import flush_memory
from agentcore.memory import MemoryService

EXIT_CONFIG_ERROR: Final = 2
MAX_BASE_URL_CHARS: Final = 500
PREVIEW_CHARS: Final = 120
CHANNEL: Final = "cli"
CLI_USER: Final = "cli-user"
DATABASE_URL_ENV: Final = "AGENT_DATABASE_URL"
HELP: Final = (
    "Commands: /new (start a new session), /sessions (recent sessions), /prompt (show what the model gets), "
    "/context (context size), /compact (summarise older turns now), /memory (saved notes), "
    "/trace (timings of the last turn), /exit (quit), /help (this help)\n"
)
RECENT_SESSIONS: Final = 10
CLI_LOCK_WAIT_S: Final = 30.0
DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8088


def main(argv: Sequence[str] | None = None) -> int:
    _use_utf8_text_streams()
    parser = argparse.ArgumentParser(prog="agent", description="General-purpose agent")
    commands = parser.add_subparsers(dest="command", required=True)
    chat = commands.add_parser("chat", help="Chat with an agent in the terminal")
    chat.add_argument(
        "--profile", type=Path, required=True, help="agent folder (with agent.toml) or a TOML profile"
    )
    chat.add_argument("--fake", action="store_true", help="use an echo model: no provider, no API key")
    chat.add_argument("--session", default=None, help="session id to resume (default: a new random one)")
    serve = commands.add_parser("serve", help=f"Serve the HTTP gateway (needs {TOKEN_ENV})")
    serve.add_argument(
        "--profile", type=Path, required=True, help="agent folder (with agent.toml) or a TOML profile"
    )
    serve.add_argument("--fake", action="store_true", help="use an echo model: no provider, no API key")
    serve.add_argument("--host", default=DEFAULT_HOST, help=f"address to listen on (default {DEFAULT_HOST})")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    _add_model_commands(
        commands.add_parser("model", help=f"Model settings stored in the database (needs {DATABASE_URL_ENV})")
    )
    plugins = commands.add_parser("plugins", help="Plugins of an agent")
    plugin_commands = plugins.add_subparsers(dest="plugins_command", required=True)
    plugin_list = plugin_commands.add_parser(
        "list", help="every plugin found, whether the profile enables it and what it registers"
    )
    plugin_list.add_argument("--profile", type=Path, required=True, help="agent folder or TOML profile")
    db = commands.add_parser("db", help="Database administration (schema agent_rt)")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser(
        "bootstrap-role",
        help=f"create or update the runtime role {RUNTIME_ROLE} "
        f"(needs {MIGRATION_URL_ENV} and {PASSWORD_ENV})",
    )
    args = parser.parse_args(argv)
    if args.command == "db":
        return _bootstrap_role()
    if args.command == "plugins":
        return _list_plugins(args.profile)
    # psycopg's async driver cannot run on the Windows proactor loop.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    if args.command == "serve":
        work = _serve(args.profile, fake=args.fake, host=args.host, port=args.port)
    elif args.command == "model":
        work = _model(args)
    else:
        work = _chat(args.profile, fake=args.fake, session=args.session)
    try:
        return asyncio.run(work, loop_factory=loop_factory)
    except KeyboardInterrupt:
        _write("\n")
        return 0


def _add_model_commands(model: argparse.ArgumentParser) -> None:
    actions = model.add_subparsers(dest="model_command", required=True)
    for name, help_text in (
        ("show", "show the settings in effect and where each comes from (the key masked)"),
        ("set", "change stored settings; fields not given stay as they are"),
        ("clear", "remove every stored setting: back to the environment and the profile"),
        ("test", "send one tiny request with the settings in effect"),
    ):
        action = actions.add_parser(name, help=help_text)
        action.add_argument("--profile", type=Path, required=True, help="agent folder or TOML profile")
        if name != "set":
            continue
        action.add_argument("--provider", choices=get_args(Provider))
        action.add_argument("--model", dest="model_name")
        action.add_argument("--base-url", type=_http_url)
        action.add_argument("--reasoning", choices=get_args(ReasoningEffort))
        action.add_argument("--dialect", choices=get_args(OpenAIDialect))
        key = action.add_mutually_exclusive_group()
        key.add_argument("--api-key-env", metavar="NAME", help="read the API key from this variable")
        key.add_argument("--ask-key", action="store_true", help="type the API key (not echoed)")
        action.add_argument(
            "--clear",
            action="append",
            default=[],
            choices=(*SETTING_FIELDS, "api_key"),
            help="give this field back to the environment or the profile (repeatable)",
        )


def _http_url(value: str) -> str:
    if not value.startswith(("http://", "https://")) or len(value) > MAX_BASE_URL_CHARS:
        raise argparse.ArgumentTypeError("use an http(s) URL of at most 500 characters")
    return value


def _list_plugins(profile_path: Path) -> int:
    """Loads the profile's plugins as a start would, reports them and unloads them again."""
    try:
        profile = load_profile(profile_path)
        found = discover(plugin_roots(profile, os.environ))
    except (OSError, ValueError) as err:
        _write(f"error: {err}\n")
        return EXIT_CONFIG_ERROR
    error: str | None = None
    try:
        host = start_plugins(profile, os.environ, found)
    except PluginError as err:
        error = str(err)
        host = PluginHost(found.plugins, os.environ)
    statuses = host.status()
    host.close()
    shown = {
        "enabled_in_profile": profile.plugins.enabled,
        "plugins": [asdict(status) for status in statuses],
        "broken": dict(found.broken),
        "error": error,
    }
    _write(json.dumps(shown, ensure_ascii=False, indent=2) + "\n")
    return 0 if error is None else 1


async def _model(args: argparse.Namespace) -> int:
    db_url = os.environ.get(DATABASE_URL_ENV)
    if not db_url:
        _write(f"error: set {DATABASE_URL_ENV}: model settings are stored in the database\n")
        return EXIT_CONFIG_ERROR
    db = AgentDatabase(db_url)
    try:
        profile = load_profile(args.profile)
        admin = ModelAdmin(
            profile,
            os.environ,
            PostgresModelSettingsStore(db, agent=profile.agent.name),
            tenant_id=DEFAULT_TENANT,
            secret_key=os.environ.get(SECRET_KEY_ENV) or None,
        )
        if args.model_command == "show":
            shown = await admin.show()
        elif args.model_command == "clear":
            shown = await admin.clear()
        elif args.model_command == "test":
            shown = await admin.test()
        else:
            shown = await admin.update(_model_changes(args))
    except (OSError, ValueError, KeyError, SecretKeyMissingError) as err:
        _write(f"error: {err}\n")
        return EXIT_CONFIG_ERROR
    finally:
        await db.dispose()
    _write(json.dumps(shown, ensure_ascii=False, indent=2) + "\n")
    return 0 if shown.get("ok", True) else 1


def _model_changes(args: argparse.Namespace) -> dict[str, Any]:
    changes: dict[str, Any] = dict.fromkeys(args.clear)
    given = {
        "provider": args.provider,
        "model": args.model_name,
        "base_url": args.base_url,
        "reasoning": args.reasoning,
        "dialect": args.dialect,
    }
    changes.update({name: value for name, value in given.items() if value is not None})
    if args.api_key_env:
        changes["api_key"] = os.environ[args.api_key_env]
    elif args.ask_key:
        changes["api_key"] = getpass.getpass("API key: ")
    return changes


async def _serve(profile_path: Path, *, fake: bool, host: str, port: int) -> int:
    try:
        settings = GatewaySettings(
            token=os.environ.get(TOKEN_ENV, ""), admin_token=os.environ.get(ADMIN_TOKEN_ENV) or None
        )
    except ValueError as err:
        _write(f"error: {err}\n")
        return EXIT_CONFIG_ERROR
    db_url = os.environ.get(DATABASE_URL_ENV)
    db = AgentDatabase(db_url) if db_url else None
    try:
        try:
            runtime = build_runtime(load_profile(profile_path), fake=fake, env=os.environ, db=db)
        except (OSError, ValueError, ModelError) as err:
            _write(f"error: {err}\n")
            return EXIT_CONFIG_ERROR
        if db is None:
            _write(f"warning: no {DATABASE_URL_ENV}: messages and sessions live in process memory only\n")
        app = create_app(runtime.dispatcher(), settings, db=db, admin=runtime.model_admin)
        server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False))
        try:
            await server.serve()
        finally:
            runtime.close()
        return 0
    finally:
        if db is not None:
            await db.dispose()


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
        runtime = build_runtime(profile, fake=fake, env=os.environ, db=db)
    except (OSError, ValueError, ModelError) as err:
        _write(f"error: {err}\n")
        return EXIT_CONFIG_ERROR
    try:
        return await _chat_loop(profile, runtime, fake=fake, session=session, db=db)
    finally:
        runtime.close()


async def _chat_loop(
    profile: Profile, runtime: Runtime, *, fake: bool, session: str | None, db: AgentDatabase | None
) -> int:
    name = profile.agent.name
    agent, store, tracer, sessions = runtime.agent, runtime.store, runtime.tracer, runtime.sessions
    session_id = session or _new_session_id()
    lines = _stdin_lines()
    model_label = describe_model(profile, fake=fake, env=os.environ)
    storage = (
        "postgres" if db else f"in process memory (set {DATABASE_URL_ENV} to keep sessions, notes and skills)"
    )
    _write(
        f"agent '{name}' | model: {model_label} | session: {session_id}\n"
        f"sessions, notes and skills: {storage}\n{HELP}"
    )
    try:
        _write(await _open(sessions, session_id))
    except SessionOwnerError as err:
        _write(f"error: {err}\n")
        return EXIT_CONFIG_ERROR

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
            await _open(sessions, session_id)
            continue
        if text == "/sessions":
            _write(await show_sessions(sessions, session_id))
            continue
        if text == "/trace":
            _write(format_trace(await tracer.last(DEFAULT_TENANT, session_id)))
            continue
        if text.startswith("/"):
            await _command(text, agent, store, session_id)
            continue
        try:
            observer = ConsoleObserver()
            async with runtime.locks.hold(DEFAULT_TENANT, session_id, timeout_s=CLI_LOCK_WAIT_S):
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
                    hooks=agent.hooks,
                    tracer=tracer,
                )
        except SessionBusyError:
            _write("\nthe session is busy with another run; try again in a moment\n")
            continue
        except ModelError as err:
            _write(f"\nerror ({err.kind}): {err}\n")
            continue
        _write(observer.finish(result))


async def _open(sessions: PostgresSessionStore | None, session_id: str) -> str:
    if sessions is None:
        return ""
    info = await sessions.open_session(DEFAULT_TENANT, session_id, channel=CHANNEL, user_id=CLI_USER)
    return f"resumed session {session_id} ({info.message_count} messages)\n" if info.message_count else ""


async def show_sessions(sessions: PostgresSessionStore | None, current: str) -> str:
    if sessions is None:
        return f"sessions live only in this process: set {DATABASE_URL_ENV} to keep and resume them\n"
    found = await sessions.list_sessions(DEFAULT_TENANT, limit=RECENT_SESSIONS)
    if not found:
        return "no sessions yet\n"
    lines = ["recent sessions (resume with --session <id>):"]
    for info in found:
        mark = "  <- current" if info.session_id == current else ""
        updated = info.updated_at.astimezone().strftime("%Y-%m-%d %H:%M")
        lines.append(f"  {info.session_id}  {info.message_count} messages  updated {updated}{mark}")
    return "\n".join(lines) + "\n"


def format_trace(trace: TurnTrace | None) -> str:
    if trace is None:
        return "no turn traced in this session yet\n"
    outcome = f"{trace.stop} ({trace.error_kind})" if trace.error_kind else trace.stop
    usage = trace.usage
    lines = [
        f"turn {trace.turn_id[:8]}: {outcome}, {trace.steps} steps, {trace.duration_s:.2f}s, "
        f"in={usage.input_tokens} out={usage.output_tokens} cached={usage.cache_read_tokens}"
    ]
    for event in trace.events:
        label = f"{event.kind} {event.name}" if event.name else event.kind
        status = "error" if event.is_error else "ok"
        detail = ", ".join(f"{key}={value}" for key, value in event.detail.items())
        lines.append(
            f"  step {event.step}  {label}  {event.duration_s:.2f}s  {status}"
            + (f"  ({detail})" if detail else "")
        )
    return "\n".join(lines) + "\n"


def _bootstrap_role() -> int:
    url = os.environ.get(MIGRATION_URL_ENV)
    password = os.environ.get(PASSWORD_ENV)
    if not url or not password:
        _write(f"error: set {MIGRATION_URL_ENV} (an owner role) and {PASSWORD_ENV}\n")
        return EXIT_CONFIG_ERROR
    try:
        done = bootstrap_role(url, password)
    except (ValueError, psycopg.Error) as err:
        _write(f"error: {type(err).__name__}: {err}\n")
        return EXIT_CONFIG_ERROR
    _write("".join(f"{line}\n" for line in done))
    return 0


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
            hooks=agent.hooks,
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
