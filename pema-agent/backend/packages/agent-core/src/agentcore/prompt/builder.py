"""What the model sees around the conversation: the frozen system prompt and the transient context block.

The system prompt is rendered from the session sections once per session and stored with a fingerprint of the
configuration it came from (environment and section names). Later turns reuse the stored text, so content that
changes during a session never breaks the provider's prompt cache; a different configuration rebuilds it and
logs a cache break. Turn and step sections go into an ``<agent-context>`` block at the end of the request; it
is never stored.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from collections import Counter
from collections.abc import Sequence
from typing import Final

from agentcore.harness.store.base import SessionStore, StoredPrompt
from agentcore.messages import Message, TextBlock
from agentcore.prompt.sections import (
    PromptEnv,
    Section,
    SessionSection,
    StepInfo,
    StepSection,
    TurnInfo,
    TurnSection,
)

CONTEXT_OPEN: Final = "<agent-context>"
CONTEXT_CLOSE: Final = "</agent-context>"
CONTEXT_EXPLAINER: Final = (
    f"A message may end with an {CONTEXT_OPEN} block. It is runtime information added by the system, "
    "not text written by the user."
)
FINAL_TURN_NOTE: Final = (
    "The step limit for this turn has been reached. Answer the user now with what you already have. "
    "Do not call tools."
)

logger = logging.getLogger(__name__)


class PromptBuilder:
    def __init__(self, env: PromptEnv, sections: Sequence[Section]) -> None:
        names = [section.name for section in sections]
        repeated = sorted(name for name, count in Counter(names).items() if count > 1)
        if repeated:
            raise ValueError(f"Prompt section(s) listed twice: {', '.join(repeated)}")
        self._env = env
        self._session = [s for s in sections if isinstance(s, SessionSection)]
        self._dynamic = [s for s in sections if not isinstance(s, SessionSection)]
        payload = json.dumps({"env": dataclasses.asdict(env), "sections": names}, sort_keys=True)
        self._fingerprint = hashlib.sha256(payload.encode()).hexdigest()

    @classmethod
    def fixed(cls, text: str) -> PromptBuilder:
        """A system prompt of exactly ``text`` and no context block apart from the final-turn note."""
        return cls(PromptEnv(agent_name="agent", persona=text), [SessionSection("fixed", _persona)])

    @property
    def env(self) -> PromptEnv:
        return self._env

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def render_system(self) -> str:
        parts = [text for section in self._session if (text := section.render(self._env))]
        if self._dynamic:
            parts.append(CONTEXT_EXPLAINER)
        return "\n\n".join(parts)

    async def system(self, store: SessionStore, tenant_id: str, session_id: str) -> str:
        """The session's frozen system prompt, built and stored on first use."""
        saved = await store.load_prompt(tenant_id, session_id)
        if saved is not None and saved.fingerprint == self._fingerprint:
            return saved.text
        if saved is not None:
            logger.warning(
                "prompt cache break: session %s rebuilds its system prompt (configuration %s -> %s)",
                session_id,
                saved.fingerprint[:12],
                self._fingerprint[:12],
            )
        text = self.render_system()
        await store.save_prompt(tenant_id, session_id, StoredPrompt(text=text, fingerprint=self._fingerprint))
        return text

    def start_turn(self, turn: TurnInfo) -> TurnPrompt:
        return TurnPrompt(self._env, turn, self._dynamic)


class TurnPrompt:
    """The context block for each model call of one turn; turn sections are rendered once, here."""

    def __init__(self, env: PromptEnv, turn: TurnInfo, sections: Sequence[TurnSection | StepSection]) -> None:
        self._env = env
        self._turn = turn
        self._sections = list(sections)
        self._turn_texts = {s.name: s.render(env, turn) for s in self._sections if isinstance(s, TurnSection)}

    def context(self, step: StepInfo) -> str | None:
        parts: list[str] = []
        for section in self._sections:
            if isinstance(section, TurnSection):
                text = self._turn_texts[section.name]
            else:
                text = section.render(self._env, self._turn, step)
            if text:
                parts.append(text)
        if step.final:
            parts.append(FINAL_TURN_NOTE)
        if not parts:
            return None
        return "\n".join([CONTEXT_OPEN, *parts, CONTEXT_CLOSE])


def with_context(messages: Sequence[Message], context: str | None) -> list[Message]:
    """The messages to send, with the context block at the end. It joins the user's message when that is
    last, because some providers refuse two user messages in a row."""
    if context is None:
        return list(messages)
    if messages and messages[-1].role == "user":
        last = messages[-1]
        joined = last.model_copy(update={"blocks": [*last.blocks, TextBlock(text=f"\n\n{context}")]})
        return [*messages[:-1], joined]
    return [*messages, Message.user(context)]


def _persona(env: PromptEnv) -> str:
    return env.persona
