"""The Anthropic adapter (provisional, no live key yet): message mapping with cache breakpoints, thinking round
trip, stream assembly through the real SDK against a mocked transport, the reasoning map and errors."""

from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic import AsyncAnthropic

from agentcore import (
    LlmRequest,
    Message,
    ModelConfigError,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolSchema,
    ToolUseBlock,
)
from agentcore.harness.model.anthropic import (
    EMPTY_REPLY,
    AnthropicConfig,
    AnthropicModel,
    classify_anthropic_error,
    to_anthropic_messages,
    to_anthropic_system,
    to_anthropic_tools,
)
from agentcore.harness.model.reasoning import AnthropicReasoning, anthropic_reasoning

EPHEMERAL = {"type": "ephemeral"}
HTTP_REQUEST = httpx2.Request("POST", "https://anthropic.test/v1/messages")


def test_the_system_prompt_and_the_last_tool_carry_cache_breakpoints() -> None:
    request = LlmRequest(
        system="sys",
        messages=[],
        tools=[
            ToolSchema(name="a", description="A.", parameters={"type": "object"}),
            ToolSchema(name="b", description="B.", parameters={"type": "object"}),
        ],
    )

    assert to_anthropic_system(request) == [{"type": "text", "text": "sys", "cache_control": EPHEMERAL}]
    first, last = to_anthropic_tools(request)
    assert "cache_control" not in first
    assert last == {
        "name": "b",
        "description": "B.",
        "input_schema": {"type": "object"},
        "cache_control": EPHEMERAL,
    }
    assert to_anthropic_system(LlmRequest(system="", messages=[])) == []


def test_messages_map_with_tool_results_merged_into_the_next_user_message() -> None:
    messages = [
        Message.user("2+3?"),
        Message(
            role="assistant",
            blocks=[
                ThinkingBlock(text="add them", signature="sig", provider="anthropic"),
                ThinkingBlock(text="", redacted_data="opaque", provider="anthropic"),
                ThinkingBlock(text="DeepSeek reasoning", provider="deepseek"),
                TextBlock(text="checking"),
                ToolUseBlock(id="t1", name="add", args={"a": 2, "b": 3}),
            ],
        ),
        Message(role="tool", blocks=[ToolResultBlock(tool_use_id="t1", name="add", content="5")]),
        Message.user("<agent-context>step 2</agent-context>"),
    ]

    assert to_anthropic_messages(messages) == [
        {"role": "user", "content": [{"type": "text", "text": "2+3?"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "add them", "signature": "sig"},
                {"type": "redacted_thinking", "data": "opaque"},
                {"type": "text", "text": "checking"},
                {"type": "tool_use", "id": "t1", "name": "add", "input": {"a": 2, "b": 3}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "5", "is_error": False},
                {"type": "text", "text": "<agent-context>step 2</agent-context>", "cache_control": EPHEMERAL},
            ],
        },
    ]


def test_an_assistant_message_with_nothing_to_send_gets_a_placeholder() -> None:
    messages = [Message.user("hi"), Message(role="assistant", blocks=[TextBlock(text="")]), Message.user("?")]

    mapped = to_anthropic_messages(messages)

    assert mapped[1] == {"role": "assistant", "content": [{"type": "text", "text": EMPTY_REPLY}]}


@pytest.mark.parametrize(
    ("effort", "expected"),
    [
        (None, AnthropicReasoning()),
        ("off", AnthropicReasoning(thinking="disabled")),
        ("low", AnthropicReasoning(thinking="adaptive", effort="low")),
        ("high", AnthropicReasoning(thinking="adaptive", effort="high")),
    ],
)
def test_the_reasoning_effort_maps_to_adaptive_thinking(effort: Any, expected: AnthropicReasoning) -> None:
    assert anthropic_reasoning(effort) == expected


def _sse(*events: dict[str, Any]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


STREAM = _sse(
    {
        "type": "message_start",
        "message": {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "m",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 1,
                "cache_read_input_tokens": 5,
                "cache_creation_input_tokens": 2,
            },
        },
    },
    {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "thinking", "thinking": "", "signature": ""},
    },
    {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Cộng lại"}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig-1"}},
    {"type": "content_block_stop", "index": 0},
    {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Để tôi tính"}},
    {"type": "content_block_stop", "index": 1},
    {
        "type": "content_block_start",
        "index": 2,
        "content_block": {"type": "tool_use", "id": "tu_1", "name": "add", "input": {}},
    },
    {
        "type": "content_block_delta",
        "index": 2,
        "delta": {"type": "input_json_delta", "partial_json": '{"a": 2, "b": 3}'},
    },
    {"type": "content_block_stop", "index": 2},
    {
        "type": "message_delta",
        "delta": {"stop_reason": "tool_use", "stop_sequence": None},
        "usage": {"output_tokens": 42},
    },
    {"type": "message_stop"},
)


class _Sink:
    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.thinking_parts: list[str] = []

    def text(self, delta: str) -> None:
        self.text_parts.append(delta)

    def thinking(self, delta: str) -> None:
        self.thinking_parts.append(delta)


async def _complete(request: LlmRequest, sink: _Sink | None = None) -> tuple[Any, dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def handler(http_request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(http_request.content))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=STREAM)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        client = AsyncAnthropic(
            api_key="k", base_url="https://anthropic.test", max_retries=0, http_client=http
        )
        model = AnthropicModel(AnthropicConfig(model="m", api_key="k"), client=client)
        result = await model.complete(request, sink=sink)
    return result, sent[0]


async def test_a_streamed_reply_is_assembled_with_signed_thinking_and_normalised_usage() -> None:
    sink = _Sink()
    request = LlmRequest(
        system="sys",
        messages=[Message.user("2+3?")],
        tools=[ToolSchema(name="add", description="Add.", parameters={"type": "object"})],
        max_output_tokens=256,
        reasoning="low",
    )

    result, body = await _complete(request, sink)

    thinking, text, use = result.message.blocks
    assert thinking == ThinkingBlock(text="Cộng lại", signature="sig-1", provider="anthropic")
    assert text == TextBlock(text="Để tôi tính")
    assert (use.name, use.args) == ("add", {"a": 2, "b": 3})
    assert result.stop_reason == "tool_use"
    usage = result.message.usage
    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens, usage.cache_read_tokens, usage.cache_write_tokens) == (
        17,
        42,
        5,
        2,
    )
    assert (sink.thinking_parts, sink.text_parts) == (["Cộng lại"], ["Để tôi tính"])
    assert body["model"] == "m"
    assert body["max_tokens"] == 256
    assert body["stream"] is True
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"] == {"effort": "low"}
    assert body["system"][0]["cache_control"] == EPHEMERAL


async def test_without_a_reasoning_effort_no_thinking_parameter_is_sent() -> None:
    _, body = await _complete(LlmRequest(system="", messages=[Message.user("hi")]))

    assert "thinking" not in body
    assert "output_config" not in body
    assert "system" not in body
    assert "tools" not in body


def _status_error(cls: type[anthropic.APIStatusError], status: int, message: str) -> anthropic.APIStatusError:
    return cls(message, response=httpx2.Response(status, request=HTTP_REQUEST), body=None)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (_status_error(anthropic.AuthenticationError, 401, "invalid x-api-key"), "auth"),
        (_status_error(anthropic.PermissionDeniedError, 403, "no"), "auth"),
        (_status_error(anthropic.RateLimitError, 429, "slow down"), "rate_limit"),
        (_status_error(anthropic.RequestTooLargeError, 413, "too large"), "context_overflow"),
        (
            _status_error(anthropic.BadRequestError, 400, "prompt is too long: 210000 tokens"),
            "context_overflow",
        ),
        (_status_error(anthropic.BadRequestError, 400, "invalid tool schema"), "unknown"),
        (_status_error(anthropic.InternalServerError, 529, "Overloaded"), "transient"),
        (anthropic.APIConnectionError(request=HTTP_REQUEST), "transient"),
    ],
)
def test_provider_errors_are_classified(error: anthropic.APIError, kind: str) -> None:
    assert classify_anthropic_error(error).kind == kind


@pytest.mark.parametrize(("model", "api_key", "field"), [("", "k", "model"), ("m", " ", "api_key")])
def test_missing_configuration_is_a_config_error(model: str, api_key: str, field: str) -> None:
    with pytest.raises(ModelConfigError) as caught:
        AnthropicModel(AnthropicConfig(model=model, api_key=api_key))

    assert caught.value.field == field
