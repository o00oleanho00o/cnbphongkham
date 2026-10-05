# ported from: none (new: the adapter replaces @ai-sdk/google; behaviour mirrors llm-provider.ts)
"""The Gemini adapter against a fake ``genai`` client (no network): stream aggregation, usage, function calls
with ``thought_signature`` round trip, message conversion, error conversion."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors as genai_errors
from google.genai import types

from pema.agent.model_types import ModelRequest, ToolSchema
from pema.agent.providers.errors import ProviderCallError, is_retryable_error
from pema.agent.providers.gemini_adapter import GeminiModel, to_gemini_contents


def _chunk(parts: list[types.Part], *, finish: str | None = None, usage: Any = None) -> Any:
    candidate = SimpleNamespace(
        finish_reason=SimpleNamespace(name=finish) if finish else None,
        content=SimpleNamespace(parts=parts),
    )
    return SimpleNamespace(candidates=[candidate], usage_metadata=usage, model_version="gemini-test-001")


class _FakeModels:
    def __init__(self, chunks: list[Any], error: Exception | None = None) -> None:
        self._chunks = chunks
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def generate_content_stream(self, **kwargs: Any) -> AsyncIterator[Any]:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error

        async def gen() -> AsyncIterator[Any]:
            for chunk in self._chunks:
                yield chunk

        return gen()


def _model(chunks: list[Any], error: Exception | None = None) -> tuple[GeminiModel, _FakeModels]:
    models = _FakeModels(chunks, error)
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiModel(api_key="test-key", model="gemini-test", client=client), models


def _ping() -> ModelRequest:
    return ModelRequest(system="", messages=[{"role": "user", "content": "."}])


async def test_text_thoughts_and_usage_are_aggregated() -> None:
    """gom text, tách thought, cộng usage (thoughts tính vào output)"""
    usage = types.UsageMetadata(
        prompt_token_count=100,
        response_token_count=20,
        thoughts_token_count=10,
        total_token_count=130,
        cached_content_token_count=5,
    )
    model, models = _model(
        [
            _chunk([types.Part(text="đang nghĩ", thought=True)]),
            _chunk([types.Part(text="Xin ")]),
            _chunk([types.Part(text="chào")], finish="STOP", usage=usage),
        ]
    )
    out = await model.complete(
        ModelRequest(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            max_output_tokens=300,
            provider_options={"google": {"thinkingConfig": {"thinkingLevel": "high"}}},
            timeout_s=30,
        )
    )
    assert out.text == "Xin chào"
    assert out.reasoning_text == "đang nghĩ"
    assert out.finish_reason == "stop"
    assert (out.usage.input_tokens, out.usage.output_tokens, out.usage.total_tokens) == (100, 30, 130)
    assert (out.usage.reasoning_tokens, out.usage.cache_read_tokens) == (10, 5)
    assert out.model_id == "gemini-test-001"
    config = models.calls[0]["config"]
    assert config.system_instruction == "sys"
    assert config.max_output_tokens == 300
    assert str(config.thinking_config.thinking_level.value).lower() == "high"
    assert config.http_options.timeout == 30_000


async def test_function_call_carries_the_thought_signature_back() -> None:
    """function call giữ thought_signature để gửi lại lượt sau (Gemini 3 bắt buộc)"""
    call = types.FunctionCall(name="get_datetime", args={"tz": "vn"})
    model, models = _model(
        [_chunk([types.Part(function_call=call, thought_signature=b"sig-bytes")], finish="STOP")]
    )
    out = await model.complete(
        ModelRequest(
            system="",
            messages=[{"role": "user", "content": "mấy giờ"}],
            tools=[ToolSchema("get_datetime", "d", {"type": "object", "properties": {}})],
        )
    )
    assert out.finish_reason == "tool-calls"
    [tool_call] = out.tool_calls
    assert (tool_call.tool_name, tool_call.input) == ("get_datetime", {"tz": "vn"})
    assert tool_call.provider_options == {
        "google": {"thoughtSignature": base64.b64encode(b"sig-bytes").decode()}
    }
    declared = models.calls[0]["config"].tools[0].function_declarations[0]
    assert declared.name == "get_datetime"
    assert models.calls[0]["config"].automatic_function_calling.disable is True

    # the signature goes back in the next request, as the bytes the API returned
    assistant: dict[str, Any] = {
        "role": "assistant",
        "content": [
            {
                "type": "tool-call",
                "toolCallId": tool_call.tool_call_id,
                "toolName": tool_call.tool_name,
                "input": tool_call.input,
                "providerOptions": tool_call.provider_options,
            }
        ],
    }
    contents, _ = to_gemini_contents([{"role": "user", "content": "q"}, assistant])
    assert contents[1].role == "model"
    assert contents[1].parts is not None
    assert contents[1].parts[0].thought_signature == b"sig-bytes"


def test_tool_results_and_adjacent_user_turns_merge() -> None:
    """kết quả tool và tin user liền nhau gộp một lượt user"""
    result = {
        "type": "tool-result",
        "toolCallId": "c1",
        "toolName": "web_fetch",
        "output": {"type": "error-text", "value": "hỏng"},
    }
    contents, warnings = to_gemini_contents(
        [
            {"role": "tool", "content": [result]},
            {"role": "user", "content": [{"type": "text", "text": "vừa nhắn thêm"}]},
        ]
    )
    assert warnings == []
    assert len(contents) == 1
    assert contents[0].role == "user"
    assert contents[0].parts is not None
    response = contents[0].parts[0].function_response
    assert response is not None
    assert (response.name, response.response) == ("web_fetch", {"error": "hỏng"})
    assert contents[0].parts[1].text == "vừa nhắn thêm"


def test_images_become_inline_data_and_other_files_are_dropped() -> None:
    """ảnh thành inline_data; file khác bị bỏ kèm cảnh báo"""
    contents, warnings = to_gemini_contents(
        [
            {
                "role": "user",
                "content": [
                    {"type": "file", "data": base64.b64encode(b"ABC").decode(), "mediaType": "image/png"},
                    {"type": "file", "data": "eA==", "mediaType": "application/pdf"},
                ],
            }
        ]
    )
    assert contents[0].parts is not None
    assert len(contents[0].parts) == 1
    blob = contents[0].parts[0].inline_data
    assert blob is not None
    assert (blob.data, blob.mime_type) == (b"ABC", "image/png")
    assert len(warnings) == 1


@pytest.mark.parametrize(("code", "retryable"), [(401, False), (400, False), (429, True), (503, True)])
async def test_api_errors_become_provider_call_error(code: int, retryable: bool) -> None:
    """lỗi API thành ProviderCallError với mã HTTP"""
    api_error = genai_errors.APIError(code, {"error": {"message": "boom", "status": "X"}})
    model, _ = _model([], error=api_error)
    with pytest.raises(ProviderCallError) as caught:
        await model.complete(_ping())
    assert caught.value.status_code == code
    assert is_retryable_error(caught.value) is retryable
