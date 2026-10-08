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
from agent_app.profile import load_profile
from agentcore import (
    InMemorySessionStore,
    ModelError,
    ToolResultBlock,
    ToolUseBlock,
    TurnResult,
    run_turn,
)
from agentcore.harness.tools.builtin import builtin_tools

EXIT_CONFIG_ERROR: Final = 2
PREVIEW_CHARS: Final = 120
HELP: Final = "Commands: /new (start a new session), /exit (quit), /help (this help)\n"


def main(argv: Sequence[str] | None = None) -> int:
    _tolerate_unencodable_output()
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
        model = build_model(profile, fake=fake, env=os.environ)
    except (OSError, ValueError, ModelError) as err:
        _write(f"error: {err}\n")
        return EXIT_CONFIG_ERROR

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
        try:
            result = await run_turn(
                session_id=session_id,
                user_text=text,
                system_prompt=profile.agent.system_prompt,
                model=model,
                tools=tools,
                store=store,
                policy=profile.loop_policy(),
            )
        except ModelError as err:
            _write(f"error ({err.kind}): {err}\n")
            continue
        _write(render_turn(result))


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
    lines.append(
        f"  (steps={result.steps}, in={usage.input_tokens}, out={usage.output_tokens}, stop={result.stop})"
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


def _tolerate_unencodable_output() -> None:
    # A console or pipe in a legacy code page cannot print every character of a reply: replace, do not crash.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(errors="replace")


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
