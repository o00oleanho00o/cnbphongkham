"""``OllamaEmbeddingClient`` (OpenAI-compatible ``/embeddings``) without a network: ``httpx.MockTransport``.
New tests (no original). Running against a REAL Ollama is described in ``kb-samples/README.md``."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pema.knowledge.embedding_client import (
    EmbeddingError,
    EmbeddingSettings,
    OllamaEmbeddingClient,
    kiem_tra_dia_chi_noi_bo,
    la_dia_chi_noi_bo,
)
from pema_contracts.knowledge import KB_EMBEDDING_DIMENSIONS


def _vector(i: int) -> list[float]:
    v = [0.0] * KB_EMBEDDING_DIMENSIONS
    v[i] = 1.0
    return v


def _client(handler: httpx.MockTransport, **ghi_de: object) -> OllamaEmbeddingClient:
    settings = EmbeddingSettings(base_url="http://localhost:11434/v1", batch_size=2, **ghi_de)  # type: ignore[arg-type]
    return OllamaEmbeddingClient(settings, transport=handler)


async def test_embed_posts_batches_to_the_openai_compatible_endpoint_and_keeps_the_order() -> None:
    """embed: gửi theo lô tới /embeddings, giữ đúng thứ tự (kể cả khi server trả lẫn thứ tự)"""
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        body = json.loads(request.content)
        requests.append(body)
        data = [{"index": i, "embedding": _vector(len(requests) * 10 + i)} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": list(reversed(data))})

    client = _client(httpx.MockTransport(handler))
    out = await client.embed(["a", "b", "c"])
    assert [r["input"] for r in requests] == [["a", "b"], ["c"]]
    assert all(r["model"] == "bge-m3" for r in requests)
    assert [v.index(1.0) for v in out] == [10, 11, 20]
    assert client.dimensions == KB_EMBEDDING_DIMENSIONS
    await client.aclose()


async def test_embed_refuses_a_wrong_dimension_a_wrong_count_and_a_server_error() -> None:
    """embed: sai số chiều / sai số vector / lỗi server đều ném EmbeddingError"""

    def sai_chieu(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    def thieu(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    def hong(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    for handler, mong in ((sai_chieu, "chiều"), (thieu, "không khớp"), (hong, "HTTPStatusError")):
        client = _client(httpx.MockTransport(handler))
        with pytest.raises(EmbeddingError, match=mong):
            await client.embed(["a"])
        await client.aclose()


def test_only_clinic_internal_addresses_are_accepted_by_default() -> None:
    """chỉ nhận địa chỉ trong mạng nội bộ: loopback, riêng tư, Tailscale, tên không chấm; chặn địa chỉ công cộng"""
    for host in (
        "localhost",
        "127.0.0.1",
        "192.168.1.20",
        "10.0.0.5",
        "100.101.102.103",
        "ollama",
        "gpu.ts.net",
        "pc.local",
        "::1",
    ):
        assert la_dia_chi_noi_bo(host), host
    for host in ("api.openai.com", "8.8.8.8", "embeddings.example.com", ""):
        assert not la_dia_chi_noi_bo(host), host

    with pytest.raises(EmbeddingError, match="ngoài mạng nội bộ"):
        kiem_tra_dia_chi_noi_bo("https://api.openai.com/v1", allow_remote=False)
    kiem_tra_dia_chi_noi_bo("https://api.openai.com/v1", allow_remote=True)
    with pytest.raises(EmbeddingError):
        OllamaEmbeddingClient(EmbeddingSettings(base_url="https://embeddings.example.com/v1"))


def test_embeddings_are_off_by_default_while_the_local_llm_is_paused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tạm tắt LLM local: không đặt PEMA_EMBEDDING_ENABLED thì không dựng embedder (chỉ tìm theo từ khóa)."""
    from pema.composition.app_runtime import embedder_from_env

    monkeypatch.delenv("PEMA_EMBEDDING_ENABLED", raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env file
    assert EmbeddingSettings().enabled is False
    assert embedder_from_env() is None


def test_embeddings_can_be_switched_back_on_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bật lại bằng PEMA_EMBEDDING_ENABLED=true mà không sửa code."""
    monkeypatch.setenv("PEMA_EMBEDDING_ENABLED", "true")
    assert EmbeddingSettings().enabled is True
