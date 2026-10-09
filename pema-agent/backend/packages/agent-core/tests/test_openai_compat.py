"""The OpenAI-compatible adapter: message mapping, stream assembly, error classification and one round trip
through the real SDK against a mocked HTTP transport."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx2
import openai
import pytest
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk

from agentcore import (
    LlmRequest,
    Message,
    ModelConfigError,
    ModelError,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolSchema,
    ToolUseBlock,
)
from agentcore.harness.model.errors import MAX_RETRY_AFTER_S
from agentcore.harness.model.openai_compat import (
    OpenAICompatConfig,
    OpenAICompatModel,
    assemble_stream,
    classify_openai_error,
    to_openai_messages,
    to_openai_tools,
)

HTTP_REQUEST = httpx2.Request("POST", "https://llm.test/v1/chat/completions")


def _chunk_dict(
    delta: dict[str, Any] | None = None, *, finish: str | None = None, usage: dict[str, Any] | None = None
) -> dict[str, Any]:
    choices: list[dict[str, Any]] = []
    if delta is not None or finish is not None:
        choices.append({"index": 0, "delta": delta or {}, "finish_reason": finish})
    return {
        "id": "chunk",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "m",
        "choices": choices,
        "usage": usage,
    }


def _chunk(
    delta: dict[str, Any] | None = None, *, finish: str | None = None, usage: dict[str, Any] | None = None
) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(_chunk_dict(delta, finish=finish, usage=usage))


async def _stream(*chunks: ChatCompletionChunk) -> AsyncIterator[ChatCompletionChunk]:
    for chunk in chunks:
        yield chunk


def _tool_delta(
    index: int, *, call_id: str | None = None, name: str | None = None, args: str | None = None
) -> dict[str, Any]:
    function: dict[str, Any] = {}
    if name is not None:
        function["name"] = name
    if args is not None:
        function["arguments"] = args
    call: dict[str, Any] = {"index": index, "function": function}
    if call_id is not None:
        call["id"] = call_id
        call["type"] = "function"
    return {"tool_calls": [call]}


USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def test_messages_map_to_chat_completions() -> None:
    request = LlmRequest(
        system="sys",
        messages=[
            Message.user("hi"),
            Message(
                role="assistant",
                blocks=[
                    ThinkingBlock(text="hmm", signature="sig"),
                    TextBlock(text="let me check"),
                    ToolUseBlock(id="c1", name="lookup", args={"q": "ngày mai"}),
                ],
            ),
            Message(
                role="tool", blocks=[ToolResultBlock(tool_use_id="c1", name="lookup", content="Thứ Sáu")]
            ),
            Message(role="assistant", blocks=[ToolUseBlock(id="c2", name="lookup", raw_args="{bad")]),
        ],
    )

    assert to_openai_messages(request) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "let me check",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": '{"q": "ngày mai"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "Thứ Sáu"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c2", "type": "function", "function": {"name": "lookup", "arguments": "{bad"}}
            ],
        },
    ]


def test_tools_map_to_function_tools() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    request = LlmRequest(
        system="", messages=[], tools=[ToolSchema(name="add", description="Add.", parameters=schema)]
    )

    assert to_openai_tools(request) == [
        {"type": "function", "function": {"name": "add", "description": "Add.", "parameters": schema}}
    ]
    assert to_openai_messages(request) == []


async def test_a_stream_of_text_and_split_tool_calls_is_assembled() -> None:
    result = await assemble_stream(
        _stream(
            _chunk({"content": "Hel"}),
            _chunk({"content": "lo"}),
            _chunk(_tool_delta(0, call_id="a", name="add", args='{"a":')),
            _chunk(_tool_delta(0, name="add", args=' 1, "b": 2}')),
            _chunk(_tool_delta(1, call_id="b", name="get_datetime", args="")),
            _chunk(finish="tool_calls"),
            _chunk(usage=USAGE),
        )
    )

    assert result.stop_reason == "tool_use"
    assert result.message.text() == "Hello"
    assert [(u.id, u.name, u.args, u.raw_args) for u in result.message.tool_uses()] == [
        ("a", "add", {"a": 1, "b": 2}, None),
        ("b", "get_datetime", {}, None),
    ]
    assert result.message.usage is not None
    assert (result.message.usage.input_tokens, result.message.usage.output_tokens) == (11, 7)


async def test_a_text_only_stream_ends_the_turn() -> None:
    result = await assemble_stream(_stream(_chunk({"content": "done"}), _chunk(finish="stop")))

    assert result.stop_reason == "end"
    assert result.message.tool_uses() == []


@pytest.mark.parametrize("arguments", ["{oops", "[1, 2]", '"text"'])
async def test_arguments_that_are_not_a_json_object_are_kept_raw(arguments: str) -> None:
    result = await assemble_stream(
        _stream(_chunk(_tool_delta(0, call_id="x", name="add", args=arguments)), _chunk(finish="tool_calls"))
    )

    (use,) = result.message.tool_uses()
    assert use.raw_args == arguments
    assert use.args == {}


async def test_an_empty_stream_is_an_empty_response_error() -> None:
    with pytest.raises(ModelError) as caught:
        await assemble_stream(_stream(_chunk({"content": ""}), _chunk(finish="stop"), _chunk(usage=USAGE)))

    assert caught.value.kind == "empty_response"


def _status_error(
    cls: type[openai.APIStatusError], status: int, message: str, **headers: str
) -> openai.APIStatusError:
    response = httpx2.Response(status, headers=headers, request=HTTP_REQUEST)
    return cls(message, response=response, body=None)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (_status_error(openai.AuthenticationError, 401, "Incorrect API key"), "auth"),
        (_status_error(openai.PermissionDeniedError, 403, "Not allowed"), "auth"),
        (_status_error(openai.RateLimitError, 429, "Slow down"), "rate_limit"),
        (
            _status_error(openai.BadRequestError, 400, "This model's maximum context length is 8192 tokens"),
            "context_overflow",
        ),
        (_status_error(openai.BadRequestError, 400, "Invalid value for 'temperature'"), "unknown"),
        (_status_error(openai.InternalServerError, 503, "Overloaded"), "transient"),
        (openai.APIConnectionError(request=HTTP_REQUEST), "transient"),
        (openai.APITimeoutError(request=HTTP_REQUEST), "transient"),
    ],
)
def test_provider_errors_are_classified(error: openai.APIError, kind: str) -> None:
    assert classify_openai_error(error).kind == kind


def test_retry_after_seconds_are_read_and_capped() -> None:
    assert (
        classify_openai_error(
            _status_error(openai.RateLimitError, 429, "x", **{"retry-after": "7"})
        ).retry_after_s
        == 7
    )
    capped = classify_openai_error(_status_error(openai.RateLimitError, 429, "x", **{"retry-after": "600"}))
    assert capped.retry_after_s == MAX_RETRY_AFTER_S
    assert (
        classify_openai_error(
            _status_error(openai.RateLimitError, 429, "x", **{"retry-after": "soon"})
        ).retry_after_s
        is None
    )
    assert classify_openai_error(_status_error(openai.RateLimitError, 429, "x")).retry_after_s is None


def test_retry_after_as_an_http_date_is_read() -> None:
    later = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    earlier = format_datetime(datetime.now(UTC) - timedelta(seconds=30), usegmt=True)

    waited = classify_openai_error(_status_error(openai.RateLimitError, 429, "x", **{"retry-after": later}))
    assert waited.retry_after_s is not None
    assert 25 <= waited.retry_after_s <= 30
    assert (
        classify_openai_error(
            _status_error(openai.RateLimitError, 429, "x", **{"retry-after": earlier})
        ).retry_after_s
        == 0
    )


@pytest.mark.parametrize(("model", "api_key", "field"), [("", "key", "model"), ("m", "  ", "api_key")])
def test_missing_configuration_is_a_config_error(model: str, api_key: str, field: str) -> None:
    with pytest.raises(ModelConfigError) as caught:
        OpenAICompatModel(OpenAICompatConfig(model=model, api_key=api_key))

    assert caught.value.field == field
    assert caught.value.kind == "config"


def _sse(*events: dict[str, Any]) -> bytes:
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
    return (body + "data: [DONE]\n\n").encode()


async def test_complete_streams_through_the_sdk_and_sends_the_expected_request() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        body = _sse(
            _chunk_dict(_tool_delta(0, call_id="c1", name="add", args='{"a": 2, "b": 3}')),
            _chunk_dict(finish="tool_calls"),
            _chunk_dict(usage=USAGE),
        )
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        client = AsyncOpenAI(
            api_key="test-key", base_url="https://llm.test/v1", max_retries=0, http_client=http
        )
        model = OpenAICompatModel(OpenAICompatConfig(model="m", api_key="test-key"), client=client)
        result = await model.complete(
            LlmRequest(
                system="sys",
                messages=[Message.user("2+3?")],
                tools=[ToolSchema(name="add", description="Add.", parameters={"type": "object"})],
                max_output_tokens=64,
            )
        )

    assert result.stop_reason == "tool_use"
    assert [(u.name, u.args) for u in result.message.tool_uses()] == [("add", {"a": 2, "b": 3})]
    (body,) = sent
    assert body["model"] == "m"
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    assert body["max_tokens"] == 64
    assert body["tools"][0]["function"]["name"] == "add"
    assert body["messages"][0] == {"role": "system", "content": "sys"}


async def test_complete_without_tools_sends_no_tools_field() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        body = _sse(_chunk_dict({"content": "hi"}), _chunk_dict(finish="stop"))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        client = AsyncOpenAI(
            api_key="test-key", base_url="https://llm.test/v1", max_retries=0, http_client=http
        )
        model = OpenAICompatModel(OpenAICompatConfig(model="m", api_key="test-key"), client=client)
        result = await model.complete(LlmRequest(system="", messages=[Message.user("hi")]))

    assert result.message.text() == "hi"
    assert "tools" not in sent[0]


async def test_a_rejected_key_becomes_an_auth_error_without_the_key_in_it() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        error = {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}}
        return httpx2.Response(
            401, headers={"content-type": "application/json"}, content=json.dumps(error).encode()
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        client = AsyncOpenAI(
            api_key="test-key", base_url="https://llm.test/v1", max_retries=0, http_client=http
        )
        model = OpenAICompatModel(OpenAICompatConfig(model="m", api_key="test-key"), client=client)
        with pytest.raises(ModelError) as caught:
            await model.complete(LlmRequest(system="", messages=[Message.user("hi")]))

    assert caught.value.kind == "auth"
    assert "test-key" not in str(caught.value)


class _Sink:
    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.thinking_parts: list[str] = []

    def text(self, delta: str) -> None:
        self.text_parts.append(delta)

    def thinking(self, delta: str) -> None:
        self.thinking_parts.append(delta)


async def test_reasoning_content_becomes_a_thinking_block_and_both_streams_reach_the_sink() -> None:
    sink = _Sink()
    usage = {
        **USAGE,
        "prompt_tokens_details": {"cached_tokens": 4},
        "completion_tokens_details": {"reasoning_tokens": 3},
    }

    result = await assemble_stream(
        _stream(
            _chunk({"reasoning_content": "Hôm nay "}),
            _chunk({"reasoning_content": "là thứ Sáu."}),
            _chunk({"content": "Thứ "}),
            _chunk({"content": "Sáu"}),
            _chunk(finish="stop"),
            _chunk(usage=usage),
        ),
        sink=sink,
        reasoning_provider="deepseek",
    )

    thinking, text = result.message.blocks
    assert thinking == ThinkingBlock(text="Hôm nay là thứ Sáu.", provider="deepseek")
    assert text == TextBlock(text="Thứ Sáu")
    assert (sink.thinking_parts, sink.text_parts) == (["Hôm nay ", "là thứ Sáu."], ["Thứ ", "Sáu"])
    assert result.message.usage is not None
    assert (result.message.usage.cache_read_tokens, result.message.usage.reasoning_tokens) == (4, 3)


async def test_deepseek_cache_hits_are_read_from_its_own_usage_field() -> None:
    result = await assemble_stream(
        _stream(_chunk({"content": "ok"}), _chunk(usage={**USAGE, "prompt_cache_hit_tokens": 9}))
    )

    assert result.message.usage is not None
    assert result.message.usage.cache_read_tokens == 9


async def test_reasoning_alone_is_still_an_empty_response() -> None:
    with pytest.raises(ModelError) as caught:
        await assemble_stream(_stream(_chunk({"reasoning_content": "hmm"}), _chunk(finish="stop")))

    assert caught.value.kind == "empty_response"


def _thinking_turn() -> LlmRequest:
    return LlmRequest(
        system="",
        messages=[
            Message.user("hi"),
            Message(
                role="assistant",
                blocks=[
                    ThinkingBlock(text="DeepSeek thought", provider="deepseek"),
                    ThinkingBlock(text="Claude thought", signature="s", provider="anthropic"),
                    TextBlock(text="hello"),
                ],
            ),
        ],
    )


def test_deepseek_gets_its_own_reasoning_back_and_nobody_else_does() -> None:
    deepseek = to_openai_messages(_thinking_turn(), dialect="deepseek")
    plain = to_openai_messages(_thinking_turn(), dialect="openai")

    assert deepseek[1] == {"role": "assistant", "content": "hello", "reasoning_content": "DeepSeek thought"}
    assert plain[1] == {"role": "assistant", "content": "hello"}


@pytest.mark.parametrize(
    ("base_url", "dialect", "expected"),
    [
        ("https://api.deepseek.com", None, "deepseek"),
        ("https://api.deepseek.com/v1", None, "deepseek"),
        ("https://notdeepseek.com/v1", None, "openai"),
        (None, None, "openai"),
        ("https://gateway.test/v1", "deepseek", "deepseek"),
    ],
)
def test_the_dialect_is_guessed_from_the_host_unless_set(
    base_url: str | None, dialect: Any, expected: str
) -> None:
    config = OpenAICompatConfig(model="m", api_key="k", base_url=base_url, dialect=dialect)

    assert config.resolved_dialect() == expected


async def _sent_body(base_url: str, reasoning: Any) -> dict[str, Any]:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        body = _sse(_chunk_dict({"content": "hi"}), _chunk_dict(finish="stop"))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        client = AsyncOpenAI(api_key="k", base_url=base_url, max_retries=0, http_client=http)
        model = OpenAICompatModel(
            OpenAICompatConfig(model="m", api_key="k", base_url=base_url), client=client
        )
        await model.complete(LlmRequest(system="", messages=[Message.user("hi")], reasoning=reasoning))
    return sent[0]


@pytest.mark.parametrize(
    ("base_url", "reasoning", "effort", "thinking"),
    [
        ("https://api.deepseek.com", "off", None, {"type": "disabled"}),
        ("https://api.deepseek.com", "low", "low", {"type": "enabled"}),
        ("https://api.deepseek.com", "high", "high", {"type": "enabled"}),
        ("https://api.deepseek.com", None, None, None),
        ("https://llm.test/v1", "medium", "medium", None),
        ("https://llm.test/v1", "off", None, None),
    ],
)
async def test_the_reasoning_effort_becomes_the_dialects_parameters(
    base_url: str, reasoning: Any, effort: str | None, thinking: dict[str, str] | None
) -> None:
    body = await _sent_body(base_url, reasoning)

    assert body.get("reasoning_effort") == effort
    assert body.get("thinking") == thinking
