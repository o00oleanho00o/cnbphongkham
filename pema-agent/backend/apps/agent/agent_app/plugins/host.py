"""Loads plugins, gives them a context to register through, and unloads them again.

A plugin is a folder with a manifest and a Python module whose ``register(ctx)`` adds tools, prompt sections
and hooks through ``ctx``. Every registration returns a function that undoes it; disabling a plugin undoes
them in reverse order. The host's ``version`` grows with every change, so the agent knows when to rebuild its
tools, prompt and hooks. Plugins are trusted local code: they run in this process, unsandboxed.
"""

from __future__ import annotations

import importlib.util
import itertools
import logging
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Final

from agent_app.plugins.manifest import PluginError, PluginSource
from agentcore import ToolSpec
from agentcore.harness.hooks import Hook
from agentcore.prompt import SessionSection, StepSection, TurnSection

REGISTER: Final = "register"

Disposer = Callable[[], None]
Section = SessionSection | TurnSection | StepSection


@dataclass(frozen=True, slots=True)
class Contributions:
    """Everything the enabled plugins registered, in plugin order then registration order."""

    tools: tuple[ToolSpec[Any], ...] = ()
    sections: tuple[Section, ...] = ()
    hooks: tuple[Hook, ...] = ()


@dataclass(slots=True)
class _Loaded:
    source: PluginSource
    module_name: str
    config: Mapping[str, Any]
    tools: list[ToolSpec[Any]] = field(default_factory=list[ToolSpec[Any]])
    sections: list[Section] = field(default_factory=list[Section])
    hooks: list[Hook] = field(default_factory=list[Hook])
    disposers: list[Disposer] = field(default_factory=list[Disposer])


class PluginContext:
    """What a plugin's ``register(ctx)`` receives."""

    def __init__(self, loaded: _Loaded, env: Mapping[str, str], changed: Callable[[], None]) -> None:
        self._loaded = loaded
        self._env = env
        self._changed = changed
        self.logger = logging.getLogger(f"agent_plugin.{loaded.source.name}")

    @property
    def name(self) -> str:
        return self._loaded.source.name

    @property
    def config(self) -> Mapping[str, Any]:
        """``user_config`` defaults overlaid with the settings given for this agent."""
        return self._loaded.config

    def secret(self, name: str) -> str:
        """An environment variable the manifest lists in ``requires_env``; others are not readable."""
        if name not in self._loaded.source.manifest.requires_env:
            raise PluginError(self.name, f"{name} is not in requires_env")
        return self._env[name]

    def register_tool(self, spec: ToolSpec[Any]) -> Disposer:
        return self._add(self._loaded.tools, spec)

    def register_prompt_section(self, section: Section) -> Disposer:
        return self._add(self._loaded.sections, section)

    def register_hook(self, hook: Hook) -> Disposer:
        return self._add(self._loaded.hooks, hook)

    def on_disable(self, callback: Callable[[], None]) -> Disposer:
        """Runs when the plugin is disabled, after its later registrations are undone."""
        self._loaded.disposers.append(callback)
        return callback

    def _add[T](self, items: list[T], item: T) -> Disposer:
        items.append(item)
        self._changed()

        def dispose() -> None:
            if item in items:
                items.remove(item)
                self._changed()

        self._loaded.disposers.append(dispose)
        return dispose


@dataclass(frozen=True, slots=True)
class PluginStatus:
    name: str
    version: str
    origin: str
    folder: str
    description: str
    enabled: bool
    tools: tuple[str, ...]
    sections: tuple[str, ...]
    hooks: tuple[str, ...]


class PluginHost:
    def __init__(self, sources: Mapping[str, PluginSource], env: Mapping[str, str]) -> None:
        self._sources = dict(sources)
        self._env = env
        self._loaded: dict[str, _Loaded] = {}
        self._generation = itertools.count(1)
        self.version = 0

    @property
    def sources(self) -> Mapping[str, PluginSource]:
        return self._sources

    def enabled(self) -> list[str]:
        return list(self._loaded)

    def enable(self, name: str, config: Mapping[str, Any] | None = None) -> None:
        """Loads the plugin and runs its ``register(ctx)``. On any error nothing it registered stays."""
        if name in self._loaded:
            return
        source = self._sources.get(name)
        if source is None:
            raise PluginError(name, f"not found (known: {', '.join(sorted(self._sources)) or 'none'})")
        manifest = source.manifest
        missing_env = [env_name for env_name in manifest.requires_env if not self._env.get(env_name)]
        if missing_env:
            raise PluginError(name, f"set the environment variable(s) {', '.join(missing_env)}")
        merged = {**manifest.defaults(), **(config or {})}
        missing = [key for key, spec in manifest.user_config.items() if spec.required and key not in merged]
        if missing:
            raise PluginError(name, f"missing setting(s): {', '.join(missing)}")
        module_name = f"agent_plugin_{name.replace('-', '_')}_{next(self._generation)}"
        loaded = _Loaded(source, module_name, merged)
        try:
            module = _import(source, module_name)
            register = getattr(module, REGISTER, None)
            if not callable(register):
                raise PluginError(name, f"{source.entry_path} has no {REGISTER}(ctx) function")
            register(PluginContext(loaded, self._env, self._bump))
            self._check_unique(loaded)
        except Exception as err:
            _dispose(loaded)
            _forget(module_name)
            if isinstance(err, PluginError):
                raise
            raise PluginError(name, f"failed to load: {type(err).__name__}: {err}") from err
        self._loaded[name] = loaded
        self._bump()

    def disable(self, name: str) -> None:
        loaded = self._loaded.pop(name, None)
        if loaded is None:
            return
        _dispose(loaded)
        _forget(loaded.module_name)
        self._bump()

    def close(self) -> None:
        for name in reversed(list(self._loaded)):
            self.disable(name)

    def contributions(self) -> Contributions:
        loaded = list(self._loaded.values())
        return Contributions(
            tools=tuple(t for p in loaded for t in p.tools),
            sections=tuple(s for p in loaded for s in p.sections),
            hooks=tuple(h for p in loaded for h in p.hooks),
        )

    def status(self) -> list[PluginStatus]:
        statuses: list[PluginStatus] = []
        for name, source in sorted(self._sources.items()):
            loaded = self._loaded.get(name)
            statuses.append(
                PluginStatus(
                    name=name,
                    version=source.manifest.version,
                    origin=source.origin,
                    folder=str(source.folder),
                    description=source.manifest.description,
                    enabled=loaded is not None,
                    tools=tuple(t.name for t in loaded.tools) if loaded else (),
                    sections=tuple(s.name for s in loaded.sections) if loaded else (),
                    hooks=tuple(h.name for h in loaded.hooks) if loaded else (),
                )
            )
        return statuses

    def _check_unique(self, candidate: _Loaded) -> None:
        for other in self._loaded.values():
            for kind, mine, theirs in (
                ("tool", {t.name for t in candidate.tools}, {t.name for t in other.tools}),
                ("prompt section", {s.name for s in candidate.sections}, {s.name for s in other.sections}),
            ):
                clash = sorted(mine & theirs)
                if clash:
                    raise PluginError(
                        candidate.source.name,
                        f"{kind} {', '.join(clash)} already comes from {other.source.name}",
                    )

    def _bump(self) -> None:
        self.version += 1


def _import(source: PluginSource, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name, source.entry_path, submodule_search_locations=[str(source.folder)]
    )
    if spec is None or spec.loader is None:
        raise PluginError(source.name, f"cannot import {source.entry_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # before running it, so the plugin's relative imports resolve
    spec.loader.exec_module(module)
    return module


def _dispose(loaded: _Loaded) -> None:
    logger = logging.getLogger(__name__)
    for dispose in reversed(loaded.disposers):
        try:
            dispose()
        except Exception as err:  # one failing cleanup must not keep the others from running
            logger.warning("plugin %s: a cleanup failed (%s)", loaded.source.name, type(err).__name__)
    loaded.disposers.clear()


def _forget(module_name: str) -> None:
    for key in [k for k in sys.modules if k == module_name or k.startswith(f"{module_name}.")]:
        del sys.modules[key]
