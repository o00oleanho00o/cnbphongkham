"""The agent as it stands now: rebuilt (tools, prompt, hooks) whenever the enabled plugins change.

Memory, skills and the model are created once and reused by every rebuild, so in-process notes survive a
plugin being switched on or off. A session whose system prompt was frozen with another set of tools gets it
rebuilt on its next turn (the prompt fingerprint changes).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from agent_app.assembly import Agent
from agent_app.plugins import Contributions, PluginError, PluginHost
from agentcore import ModelClient


class LiveAgent:
    def __init__(self, build: Callable[[Contributions], Agent], host: PluginHost) -> None:
        self._build: Callable[[Contributions], Agent] = build
        self._host = host
        self._version = host.version
        self._agent = build(host.contributions())

    @property
    def host(self) -> PluginHost:
        return self._host

    def current(self) -> Agent:
        if self._version != self._host.version:
            version = self._host.version
            self._agent = self._build(self._host.contributions())
            self._version = version
        return self._agent

    def enable(self, name: str, config: Mapping[str, Any] | None = None) -> None:
        """Enables a plugin while running. If the agent cannot be built with it (a tool or prompt section
        clashing with a built-in one), it is disabled again and the error names it."""
        self._host.enable(name, config)
        try:
            self.current()
        except ValueError as err:
            self._host.disable(name)
            raise PluginError(name, str(err)) from err

    def disable(self, name: str) -> None:
        self._host.disable(name)

    def use_model(self, model: ModelClient) -> None:
        """Every build from now on talks to ``model`` (tests use it to script the model)."""
        build = self._build

        def with_model(plugins: Contributions) -> Agent:
            return replace(build(plugins), model=model)

        self._build = with_model
        self._agent = replace(self._agent, model=model)
