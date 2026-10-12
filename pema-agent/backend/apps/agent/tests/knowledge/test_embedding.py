"""The embedding client against a fake OpenAI-compatible service: what it sends, what it makes of the answer,
and the sentence each failure becomes."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from plugins.knowledge.embedding import (
    EmbeddingClient,
    EmbeddingConfig,
    EmbeddingError,
)

KEY = "sk-test-synthetic"


def _config(**changes: Any) -> EmbeddingConfig:
    values: dict[str, Any] = {
        "base_url": "https://embed.test/api/v1",
        "model": "qwen/qwen3-embedding-8b",
        "dimensions": 4,
        "query_prefix": "Query: ",
        "document_prefix": "",
        "api_key": KEY,
    }
    return EmbeddingConfig(**{**values, **changes})


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> EmbeddingClient:
    return EmbeddingClient(transport=httpx.MockTransport(handler))


def _answer(
    vectors: list[list[float]], *, reverse: bool = False
) -> Callable[[httpx.Request], httpx.Response]:
    rows = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
    return lambda request: httpx.Response(200, json={"data": rows[::-1] if reverse else rows})


async def test_it_posts_the_model_the_texts_and_the_dimensions_with_the_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _answer([[1, 0, 0, 0], [0, 1, 0, 0]])(request)

    await _client(handler).embed(_config(), ["một", "hai"], timeout_s=5)

    (request,) = seen
    assert str(request.url) == "https://embed.test/api/v1/embeddings"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "model": "qwen/qwen3-embedding-8b",
        "input": ["một", "hai"],
        "dimensions": 4,
        "encoding_format": "float",
    }


@pytest.mark.parametrize("base", ["https://e.test/v1", "https://e.test/v1/", "https://e.test/v1/embeddings"])
def test_the_endpoint_is_joined_once(base: str) -> None:
    assert _config(base_url=base).endpoint == "https://e.test/v1/embeddings"


async def test_vectors_come_back_in_input_order() -> None:
    client = _client(_answer([[1, 0, 0, 0], [0, 1, 0, 0]], reverse=True))

    first, second = await client.embed(_config(), ["a", "b"], timeout_s=5)

    assert first == [1, 0, 0, 0]
    assert second == [0, 1, 0, 0]


async def test_a_longer_vector_is_cut_to_the_set_dimensions_and_normalised() -> None:
    client = _client(_answer([[3, 4, 0, 0, 9, 9, 9, 9]]))

    (vector,) = await client.embed(_config(), ["a"], timeout_s=5)

    assert len(vector) == 4
    assert vector == pytest.approx([0.6, 0.8, 0, 0])
    assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0)


async def test_a_shorter_vector_is_an_error_about_dimensions() -> None:
    client = _client(_answer([[1, 0]]))

    with pytest.raises(EmbeddingError) as raised:
        await client.embed(_config(), ["a"], timeout_s=5)

    assert raised.value.kind == "dimensions"
    assert "2 chiều" in raised.value.message


def _status(code: int, text: str = "") -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(code, text=text)


def _no_data(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"oops": 1})


def _raising(error: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


@pytest.mark.parametrize(
    ("handler", "kind", "transient", "sentence"),
    [
        (_status(401), "auth", False, "Khóa API sai"),
        (_status(403), "auth", False, "Khóa API sai"),
        (_status(404), "not_found", False, "Sai địa chỉ"),
        (_status(429), "rate_limit", True, "giới hạn"),
        (_status(500), "server", True, "HTTP 500"),
        (_status(400, '{"error": "unsupported dimensions"}'), "dimensions", False, "số chiều 4"),
        (_status(422, "nope"), "bad_response", True, "từ chối"),
        (_status(200, "not json"), "bad_response", True, "không đọc được"),
        (_no_data, "bad_response", True, "không đọc được"),
        (_raising(httpx.ReadTimeout("slow")), "timeout", True, "Quá 5 giây"),
        (_raising(httpx.ConnectError("down")), "network", True, "embed.test"),
    ],
)
async def test_errors_become_sentences(
    handler: Callable[[httpx.Request], httpx.Response], kind: str, transient: bool, sentence: str
) -> None:
    with pytest.raises(EmbeddingError) as raised:
        await _client(handler).embed(_config(), ["a"], timeout_s=5)

    assert raised.value.kind == kind
    assert raised.value.transient is transient
    assert sentence in raised.value.message
    assert KEY not in raised.value.message
    assert KEY not in repr(raised.value)


async def test_the_wrong_number_of_vectors_is_a_bad_response() -> None:
    with pytest.raises(EmbeddingError) as raised:
        await _client(_answer([[1, 0, 0, 0]])).embed(_config(), ["a", "b"], timeout_s=5)

    assert raised.value.kind == "bad_response"


async def test_a_zero_vector_is_a_bad_response() -> None:
    with pytest.raises(EmbeddingError) as raised:
        await _client(_answer([[0, 0, 0, 0]])).embed(_config(), ["a"], timeout_s=5)

    assert raised.value.kind == "bad_response"


async def test_a_config_without_a_key_is_not_ready_and_no_call_is_made() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    for config in (_config(api_key=""), _config(base_url=" "), _config(model="")):
        assert not config.ready
        with pytest.raises(EmbeddingError) as raised:
            await _client(handler).embed(config, ["a"], timeout_s=5)
        assert raised.value.kind == "config"
        assert not raised.value.transient
    assert calls == []


async def test_a_key_that_no_longer_decrypts_says_so() -> None:
    config = _config(api_key="", key_broken=True)

    with pytest.raises(EmbeddingError) as raised:
        await _client(_status(200)).embed(config, ["a"], timeout_s=5)

    assert "không giải mã được" in raised.value.message


def test_the_space_changes_with_model_dimensions_and_document_prefix_only() -> None:
    base = _config()

    assert _config(model="other").space != base.space
    assert _config(dimensions=8).space != base.space
    assert _config(document_prefix="Passage: ").space != base.space
    assert _config(query_prefix="x").space == base.space
    assert _config(base_url="https://other.test").space == base.space
    assert _config(api_key="another").space == base.space
    assert len(base.space) == 16


def test_the_key_is_not_in_the_configs_repr() -> None:
    assert KEY not in repr(_config())


async def test_a_batch_larger_than_the_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="texts per call"):
        await _client(_status(200)).embed(_config(), ["a"] * 17, timeout_s=5)


async def test_probe_reports_what_the_service_sent() -> None:
    client = _client(_answer([[3, 4, 0, 0, 0, 0]]))

    probe = await client.probe(_config())

    assert probe.dimensions == 6
    assert probe.norm == pytest.approx(5.0)
    assert probe.ms >= 0
