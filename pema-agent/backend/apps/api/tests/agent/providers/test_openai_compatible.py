# ported from: none (new: the adapter replaces @ai-sdk/openai-compatible; behaviour mirrors llm-provider.ts)
"""The OpenAI-compatible adapter against a mocked HTTP endpoint (no network): streaming aggregation, usage
(``include_usage``), tool calls, reasoning text, message conversion and error conversion."""

from __future__ import annotations

import json
from typing import Any

import pytest

from pema.agent.model_types import ModelRequest, ToolSchema
from pema.agent.providers.errors import ProviderCallError, is_retryable_error
from pema.agent.providers.http_flavour import http as httpx
from pema.agent.providers.openai_compatible import OpenAICompatibleModel, to_openai_messages


def _sse(*events: dict[str, Any]) -> bytes:
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return body.encode()


def _chunk(delta: dict[str, Any] | None = None, finish: str | None = None, **extra: Any) -> dict[str, Any]:
    choices = [] if delta is None else [{"index": 0, "delta": delta, "finish_reason": finish}]
    return {"id": "c1", "object": "chat.completion.chunk", "model": "qwen3-8b", "choices": choices, **extra}


def _model(handler: Any) -> OpenAICompatibleModel:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleModel(
        base_url="http://llm.test/v1", api_key="test-key", model="qwen3-8b", http_client=client
    )


def _ping() -> ModelRequest:
    return ModelRequest(system="", messages=[{"role": "user", "content": "."}])


async def test_streamed_text_and_usage_are_aggregated() -> None:
    """gom text stream và usage cuối (include_usage)"""
    seen: dict[str, Any] = {}

    def handler(request: Any) -> Any:
        seen["body"] = json.loads(request.content)
        seen["headers"] = request.headers
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                _chunk({"role": "assistant", "content": "Xin "}),
                _chunk({"content": "chào"}, "stop"),
                _chunk(None, usage={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}),
            ),
        )

    out = await _model(handler).complete(
        ModelRequest(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            max_output_tokens=256,
            headers={"x-session-id": "s-1"},
            provider_options={"llmRouter": {"reasoningEffort": "high"}},
        )
    )
    assert out.text == "Xin chào"
    assert out.finish_reason == "stop"
    assert (out.usage.input_tokens, out.usage.output_tokens, out.usage.total_tokens) == (120, 30, 150)
    assert out.model_id == "qwen3-8b"
    assert seen["body"]["stream"] is True
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert seen["body"]["max_tokens"] == 256
    assert seen["body"]["reasoning_effort"] == "high"
    assert "tools" not in seen["body"]
    assert seen["headers"]["x-session-id"] == "s-1"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}


async def test_tool_calls_are_assembled_from_fragments() -> None:
    """ghép tool call từ các mảnh arguments"""

    def handler(request: Any) -> Any:
        first = {"index": 0, "id": "call-1", "function": {"name": "get_datetime", "arguments": ""}}
        return httpx.Response(
            200,
            content=_sse(
                _chunk({"tool_calls": [first]}),
                _chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"tz":'}}]}),
                _chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"vn"}'}}]}, "tool_calls"),
            ),
        )

    out = await _model(handler).complete(
        ModelRequest(
            system="",
            messages=[{"role": "user", "content": "mấy giờ"}],
            tools=[ToolSchema("get_datetime", "d", {"type": "object", "properties": {}})],
        )
    )
    assert out.finish_reason == "tool-calls"
    assert [(c.tool_call_id, c.tool_name, c.input) for c in out.tool_calls] == [
        ("call-1", "get_datetime", {"tz": "vn"})
    ]


async def test_invalid_tool_arguments_are_flagged_not_raised() -> None:
    """arguments hỏng được đánh dấu để vòng lặp báo lỗi cho model"""

    def handler(request: Any) -> Any:
        call = {"index": 0, "id": "c", "function": {"name": "x", "arguments": "{oops"}}
        return httpx.Response(200, content=_sse(_chunk({"tool_calls": [call]}, "tool_calls")))

    out = await _model(handler).complete(_ping())
    assert out.tool_calls[0].invalid_input is not None


async def test_reasoning_content_is_collected() -> None:
    """reasoning_content (DeepSeek/Qwen) vào reasoning_text"""

    def handler(request: Any) -> Any:
        return httpx.Response(
            200,
            content=_sse(
                _chunk({"reasoning_content": "nghĩ "}),
                _chunk({"reasoning_content": "đã", "content": "ok"}, "stop"),
            ),
        )

    out = await _model(handler).complete(_ping())
    assert out.reasoning_text == "nghĩ đã"
    assert out.text == "ok"


@pytest.mark.parametrize(("status", "retryable"), [(401, False), (400, False), (429, True), (503, True)])
async def test_http_errors_become_provider_call_error(status: int, retryable: bool) -> None:
    """lỗi HTTP thành ProviderCallError, giữ mã và Retry-After"""

    def handler(request: Any) -> Any:
        return httpx.Response(
            status, headers={"retry-after": "7"}, json={"error": {"message": "boom", "type": "x"}}
        )

    with pytest.raises(ProviderCallError) as caught:
        await _model(handler).complete(_ping())
    assert caught.value.status_code == status
    assert caught.value.response_headers["retry-after"] == "7"
    assert is_retryable_error(caught.value) is retryable


async def test_connection_failure_is_retryable() -> None:
    """đứt kết nối thì retry được"""

    def handler(request: Any) -> Any:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderCallError) as caught:
        await _model(handler).complete(_ping())
    assert caught.value.status_code is None
    assert is_retryable_error(caught.value)


def test_message_conversion_covers_every_part_type() -> None:
    """đổi ModelMessage sang chat messages: ảnh, tool-call, tool-result"""
    call = {
        "type": "tool-call",
        "toolCallId": "c1",
        "toolName": "web_fetch",
        "input": {"url": "https://x.vn"},
    }
    result = {
        "type": "tool-result",
        "toolCallId": "c1",
        "toolName": "web_fetch",
        "output": {"type": "text", "value": "nội dung"},
    }
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "file", "data": "QUJD", "mediaType": "image/jpeg"},
                {"type": "text", "text": "ảnh gì đây"},
            ],
        },
        {"role": "assistant", "content": [call]},
        {"role": "tool", "content": [result]},
        {"role": "user", "content": "tiếp"},
    ]
    converted, warnings = to_openai_messages("hệ thống", messages)
    assert warnings == []
    assert converted[0] == {"role": "system", "content": "hệ thống"}
    image_block = {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}
    assert converted[1]["content"][0] == image_block
    assert converted[2]["tool_calls"][0]["function"] == {
        "name": "web_fetch",
        "arguments": '{"url": "https://x.vn"}',
    }
    assert converted[2]["content"] is None
    assert converted[3] == {"role": "tool", "tool_call_id": "c1", "content": "nội dung"}
    assert converted[4] == {"role": "user", "content": "tiếp"}


def test_non_image_file_parts_are_dropped_with_a_warning() -> None:
    """file không phải ảnh bị bỏ kèm cảnh báo"""
    pdf = {"type": "file", "data": "x", "mediaType": "application/pdf"}
    converted, warnings = to_openai_messages(
        "", [{"role": "user", "content": [pdf, {"type": "text", "text": "a"}]}]
    )
    assert converted == [{"role": "user", "content": "a"}]
    assert len(warnings) == 1
