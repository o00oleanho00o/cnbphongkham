"""Services plugins give each other: found by name and type while the provider is enabled, gone when it is
disabled, one provider per name; and the embedding service of the knowledge plugin as another plugin sees it."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx
import pytest

from agent_app.plugins import PluginError, PluginHost, discover
from agent_app.runtime import BUNDLED_PLUGINS
from plugin_kit import EMBEDDINGS, EmbeddingService, EmbeddingUnavailableError
from secretcipher import encrypt_with
from tests.knowledge.fake_embedding import KEY, embeddings_transport, status_transport

SECRET_KEY = "0f" * 32

PROVIDER = """
class Greeter:
    def greet(self, who):
        return f"hello {who}"


def register(ctx):
    ctx.provide("greeting", Greeter())
    if ctx.config.get("twice"):
        ctx.provide("greeting", Greeter())
"""

USER = """
def register(ctx):
    ctx.config["seen"].append(ctx.use("greeting", object))
    ctx.config["ask"].append(lambda: ctx.use("greeting", object))
"""


@runtime_checkable
class Greets(Protocol):
    def greet(self, who: str) -> str: ...


def _write(root: Path, name: str, code: str) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "plugin.toml").write_text(f'name = "{name}"\n', encoding="utf-8")
    (folder / "__init__.py").write_text(textwrap.dedent(code), encoding="utf-8")


def _host(root: Path) -> PluginHost:
    return PluginHost(discover([("agent", root)]).plugins, {})


def test_a_plugin_finds_a_service_only_while_its_provider_is_enabled_and_asks_when_it_needs_it(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "provider", PROVIDER)
    _write(tmp_path, "user", USER)
    host = _host(tmp_path)
    seen: list[Any] = []
    ask: list[Any] = []

    host.enable("user", {"seen": seen, "ask": ask})
    before = ask[0]()
    host.enable("provider")
    found = ask[0]()
    host.disable("provider")
    after = ask[0]()

    assert seen == [None]  # at registration the provider was not there yet
    assert before is None
    assert found.greet("an") == "hello an"
    assert after is None


def test_a_service_is_handed_over_only_as_the_type_asked_for(tmp_path: Path) -> None:
    _write(tmp_path, "provider", PROVIDER)
    host = _host(tmp_path)
    host.enable("provider")

    assert isinstance(host.use("greeting", Greets), Greets)
    assert host.use("greeting", str) is None
    assert host.use("missing", Greets) is None


def test_a_name_has_one_provider(tmp_path: Path) -> None:
    _write(tmp_path, "provider", PROVIDER)
    _write(tmp_path, "second", PROVIDER)
    host = _host(tmp_path)
    host.enable("provider")

    with pytest.raises(PluginError, match="service greeting already comes from provider"):
        host.enable("second")


def test_a_plugin_cannot_provide_a_name_twice(tmp_path: Path) -> None:
    _write(tmp_path, "provider", PROVIDER)
    host = _host(tmp_path)

    with pytest.raises(PluginError, match="provided twice"):
        host.enable("provider", {"twice": True})
    assert host.use("greeting", Greets) is None  # nothing it registered stays


def _knowledge(transport: httpx.AsyncBaseTransport) -> PluginHost:
    env = {"AGENT_SECRET_ENCRYPTION_KEY": SECRET_KEY}
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, env)
    host.enable("knowledge", {"embedding_transport": transport})
    return host


async def _store_key(host: PluginHost) -> None:
    """Saves the key the way the settings page does: sealed with the service's key, in the plugin's storage."""
    storage = host.storage("knowledge")
    await storage.put("embedding_api_key", encrypt_with(SECRET_KEY, KEY))
    await storage.put("settings", {"embedding": {"base_url": "https://embed.test/v1", "dimensions": 6}})


async def test_the_knowledge_plugin_gives_the_embedding_service_and_it_is_off_without_a_key() -> None:
    host = _knowledge(embeddings_transport([]))

    service = host.use(EMBEDDINGS, EmbeddingService)

    assert service is not None
    assert await service.space() is None
    with pytest.raises(EmbeddingUnavailableError):
        await service.embed_query("giá nám", timeout_s=1)
    with pytest.raises(EmbeddingUnavailableError):
        await service.embed_documents(["giá nám"], timeout_s=1)


async def test_with_a_key_the_service_embeds_documents_and_questions_in_one_space() -> None:
    calls: list[list[str]] = []
    host = _knowledge(embeddings_transport(calls))
    service = host.use(EMBEDDINGS, EmbeddingService)
    assert service is not None
    await _store_key(host)

    space = await service.space()
    vectors, made_in = await service.embed_documents(["giá nám", "huỷ lịch"], timeout_s=5)
    query, query_space = await service.embed_query("giá nám", timeout_s=5)

    assert space is not None
    assert (made_in, query_space) == (space, space)
    assert len(vectors) == 2
    assert len(query) == len(vectors[0])
    assert calls[0] == ["giá nám", "huỷ lịch"]
    assert calls[1][0].endswith("giá nám")  # the question carries the service's question prefix


async def test_a_failing_embedding_service_is_reported_as_unavailable_without_its_key() -> None:
    host = _knowledge(status_transport(500))
    service = host.use(EMBEDDINGS, EmbeddingService)
    assert service is not None
    await _store_key(host)

    with pytest.raises(EmbeddingUnavailableError) as failed:
        await service.embed_query("giá nám", timeout_s=5)

    assert KEY not in failed.value.message
