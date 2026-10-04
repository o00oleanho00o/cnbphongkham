# ported from: none (new: the adapter replaces @ai-sdk/anthropic; behaviour mirrors llm-provider.ts)
"""The Anthropic adapter against a mocked HTTP endpoint (no network): streaming aggregation, usage with cache
parts, tool use, thinking blocks with signature, message conversion (tool + user merge) and errors."""

from __future__ import annotations

import json
from typing import Any

import pytest

from pema.agent.model_types import ModelRequest, ToolSchema
from pema.agent.providers.anthropic_adapter import AnthropicModel, to_anthropic_messages
from pema.agent.providers.errors import ProviderCallError, is_retryable_error
from pema.agent.providers.http_flavour import http as httpx


def _event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n"


def _stream(blocks: list[dict[str, Any]], *, stop: str, usage: dict[str, int]) -> bytes:
    """A complete Anthropic message stream. ``blocks`` items: {"start": block, "deltas": [delta, ...]}."""
    body = _event(
        "message_start",
        {
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": usage["input"],
                    "output_tokens": 1,
                    "cache_read_input_tokens": usage.get("cache_read", 0),
                    "cache_creation_input_tokens": usage.get("cache_write", 0),
                },
            }
        },
    )
    for index, block in enumerate(blocks):
        body += _event("content_block_start", {"index": index, "content_block": block["start"]})
        for delta in block["deltas"]:
            body += _event("content_block_delta", {"index": index, "delta": delta})
        body += _event("content_block_stop", {"index": index})
    body += _event(
        "message_delta",
        {"delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": usage["output"]}},
    )
    body += _event("message_stop", {})
    return body.encode()


def _model(handler: Any) -> AnthropicModel:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AnthropicModel(api_key="test-key", model="claude-test", http_client=client)


def _ping() -> ModelRequest:
    return ModelRequest(system="", messages=[{"role": "user", "content": "."}])


async def test_text_answer_and_usage_with_cache_parts() -> None:
    """text + usage (input gồm cả phần cache) + request đúng hình dạng"""
    seen: dict[str, Any] = {}

    def handler(request: Any) -> Any:
        seen["body"] = json.loads(request.content)
        seen["headers"] = request.headers
        content = _stream(
            [{"start": {"type": "text", "text": ""}, "deltas": [{"type": "text_delta", "text": "Xin chào"}]}],
            stop="end_turn",
            usage={"input": 100, "output": 30, "cache_read": 40, "cache_write": 10},
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=content)

    out = await _model(handler).complete(
        ModelRequest(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            max_output_tokens=512,
            headers={"x-session-id": "s-1"},
            provider_options={"anthropic": {"thinking": {"type": "adaptive"}, "effort": "high"}},
        )
    )
    assert out.text == "Xin chào"
    assert out.finish_reason == "stop"
    assert out.usage.input_tokens == 150  # 100 fresh + 40 cache read + 10 cache write
    assert out.usage.output_tokens == 30
    assert out.usage.total_tokens == 180
    assert (out.usage.cache_read_tokens, out.usage.cache_write_tokens) == (40, 10)
    assert out.model_id == "claude-test"
    assert seen["body"]["system"] == "sys"
    assert seen["body"]["max_tokens"] == 512
    assert seen["body"]["thinking"] == {"type": "adaptive"}
    assert seen["body"]["output_config"] == {"effort": "high"}
    assert seen["body"]["stream"] is True
    assert seen["headers"]["x-session-id"] == "s-1"


async def test_tool_use_and_thinking_signature_round_trip() -> None:
    """tool_use thành ToolCallPart; thinking giữ chữ ký để gửi lại"""

    def handler(request: Any) -> Any:
        content = _stream(
            [
                {
                    "start": {"type": "thinking", "thinking": "", "signature": ""},
                    "deltas": [
                        {"type": "thinking_delta", "thinking": "để mình xem"},
                        {"type": "signature_delta", "signature": "sig-abc"},
                    ],
                },
                {
                    "start": {"type": "tool_use", "id": "toolu_1", "name": "get_datetime", "input": {}},
                    "deltas": [
                        {"type": "input_json_delta", "partial_json": '{"tz":'},
                        {"type": "input_json_delta", "partial_json": '"vn"}'},
                    ],
                },
            ],
            stop="tool_use",
            usage={"input": 10, "output": 5},
        )
        return httpx.Response(200, content=content)

    out = await _model(handler).complete(
        ModelRequest(
            system="",
            messages=[{"role": "user", "content": "mấy giờ"}],
            tools=[ToolSchema("get_datetime", "d", {"type": "object", "properties": {}})],
        )
    )
    assert out.finish_reason == "tool-calls"
    assert [(c.tool_call_id, c.tool_name, c.input) for c in out.tool_calls] == [
        ("toolu_1", "get_datetime", {"tz": "vn"})
    ]
    assert out.reasoning_text == "để mình xem"
    assert out.reasoning_parts == [
        {
            "type": "reasoning",
            "text": "để mình xem",
            "providerOptions": {"anthropic": {"signature": "sig-abc"}},
        }
    ]
    # the signed thinking block is written back FIRST in the next assistant turn
    assistant: dict[str, Any] = {
        "role": "assistant",
        "content": [
            *out.reasoning_parts,
            {"type": "tool-call", "toolCallId": "toolu_1", "toolName": "get_datetime", "input": {}},
        ],
    }
    converted, _ = to_anthropic_messages([{"role": "user", "content": "q"}, assistant])
    assert converted[1]["content"][0] == {
        "type": "thinking",
        "thinking": "để mình xem",
        "signature": "sig-abc",
    }
    assert converted[1]["content"][1]["type"] == "tool_use"


@pytest.mark.parametrize(("status", "retryable"), [(401, False), (400, False), (429, True), (529, True)])
async def test_http_errors_become_provider_call_error(status: int, retryable: bool) -> None:
    """lỗi HTTP thành ProviderCallError, giữ mã và Retry-After"""

    def handler(request: Any) -> Any:
        return httpx.Response(
            status,
            headers={"retry-after": "9"},
            json={"type": "error", "error": {"type": "api_error", "message": "boom"}},
        )

    with pytest.raises(ProviderCallError) as caught:
        await _model(handler).complete(_ping())
    assert caught.value.status_code == status
    assert caught.value.response_headers["retry-after"] == "9"
    assert is_retryable_error(caught.value) is retryable


def test_tool_message_and_following_user_message_merge_into_one_user_turn() -> None:
    """tool và user liền nhau gộp một khối user (chèn tin giữa lượt an toàn)"""
    result = {
        "type": "tool-result",
        "toolCallId": "t1",
        "toolName": "web_fetch",
        "output": {"type": "error-text", "value": "hỏng"},
    }
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "hỏi"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool-call", "toolCallId": "t1", "toolName": "web_fetch", "input": {"url": "x"}}
            ],
        },
        {"role": "tool", "content": [result]},
        {"role": "user", "content": [{"type": "text", "text": "vừa nhắn thêm"}]},
    ]
    converted, warnings = to_anthropic_messages(messages)
    assert warnings == []
    assert [m["role"] for m in converted] == ["user", "assistant", "user"]
    merged = converted[2]["content"]
    assert merged[0] == {"type": "tool_result", "tool_use_id": "t1", "content": "hỏng", "is_error": True}
    assert merged[1] == {"type": "text", "text": "vừa nhắn thêm"}


def test_images_and_unsupported_files() -> None:
    """ảnh thành block image base64; file khác bị bỏ kèm cảnh báo"""
    converted, warnings = to_anthropic_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "file", "data": "QUJD", "mediaType": "image/png"},
                    {"type": "file", "data": "x", "mediaType": "application/pdf"},
                    {"type": "text", "text": "gì đây"},
                ],
            }
        ]
    )
    assert converted[0]["content"][0] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"},
    }
    assert len(converted[0]["content"]) == 2
    assert len(warnings) == 1
