# ported from: src/agent/llm-provider.ts (the ``google`` branch, ``baseUrlChoGoogle``)
"""``ChatModel`` over the official ``google-genai`` SDK.

zalo-agent's comment, kept because it is the reason this adapter exists: Gemini MUST go through the vendor's
own API, NOT the OpenAI shim, because Gemini 3 returns a ``thought_signature`` with every function call and
REQUIRES it back on the next turn; the shim carries it in ``tool_calls[].extra_content`` which an
OpenAI-compatible client drops. Measured 06/08/2026: every turn WITH a tool call died with 400 "Function call
is missing a thought_signature in functionCall parts" while plain chat survived. Here the signature is stored
in the ``tool-call`` part (``providerOptions.google.thoughtSignature``, base64) and written back by
``to_gemini_contents``.

Forced deviations: ``createGoogleGenerativeAI`` becomes ``genai.Client``; the stream is read to the end and
returned as one ``ModelCompletion``; SDK errors become ``ProviderCallError`` (retrying is the loop's job, the
client is built without SDK retries). ``client`` is injectable so tests need no network.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Sequence
from typing import Any, cast
from urllib.parse import urlparse

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from pema.agent.model_types import (
    ModelCompletion,
    ModelMessage,
    ModelRequest,
    ModelUsage,
    ToolCallPart,
)
from pema.agent.providers.errors import ProviderCallError
from pema.agent.providers.messages import (
    content_parts,
    tool_output_is_error,
    tool_output_text,
)

_GOOGLE_HOST = re.compile(r"(^|\.)googleapis\.com$", re.IGNORECASE)


def base_url_cho_google(base_url: str | None) -> str | None:
    """A base URL usable for the Google provider, or ``None`` so the SDK uses the vendor's default endpoint.

    Does TWO things, both because an old base URL stays in the DB when the user changes the "connection type":

    1. STRIP THE "/openai" TAIL. Google has two endpoints on one host: the native API at ``/v1beta`` and
       the OpenAI shim at ``/v1beta/openai``. This provider speaks the native one; the shim path is a 404.
       The quick "Google Gemini" button used to fill exactly that tail, so a saved config surely has it.
    2. DROP another vendor's base URL altogether. Someone on OpenRouter or a router who switches to Google
       still has the old URL; sending the Google key there leaks it to a third party and earns a baffling
       401. Same accident that ``doi_provider_an_toan`` blocks at the provider level, so it is blocked the
       same way: better to ignore the odd config and fall back to a working state.
    """
    if not base_url:
        return None
    clean = re.sub(r"/openai$", "", base_url.strip().rstrip("/"), flags=re.IGNORECASE)
    if not clean:
        return None
    try:
        host = urlparse(clean).hostname or ""
    except ValueError:
        return None
    # Only Google's own host is accepted; a string that does not parse is ignored too
    if not _GOOGLE_HOST.search(host):
        return None
    return clean


def to_gemini_contents(messages: Sequence[ModelMessage]) -> tuple[list[types.Content], list[str]]:
    """SDK-shaped messages -> Gemini ``contents`` (adjacent same-role turns are merged)."""
    out: list[types.Content] = []
    warnings: list[str] = []

    def add(role: str, parts: list[types.Part]) -> None:
        if not parts:
            return
        if out and out[-1].role == role and out[-1].parts is not None:
            out[-1].parts.extend(parts)
        else:
            out.append(types.Content(role=role, parts=parts))

    for message in messages:
        role = message.get("role")
        parts = content_parts(message)
        if role in {"user", "tool"}:
            add("user", _user_parts(parts, warnings))
        elif role == "assistant":
            add("model", _model_parts(parts))
    return out, warnings


def _user_parts(parts: list[dict[str, Any]], warnings: list[str]) -> list[types.Part]:
    out: list[types.Part] = []
    for part in parts:
        kind = part.get("type")
        if kind == "text":
            out.append(types.Part(text=str(part.get("text", ""))))
        elif kind in {"file", "image"}:
            media_type = str(part.get("mediaType") or part.get("mimeType") or "")
            if not media_type.startswith("image/"):
                warnings.append(f"unsupported file part ({media_type or 'unknown type'}) dropped")
                continue
            data = base64.b64decode(str(part.get("data") or part.get("image") or ""))
            out.append(types.Part(inline_data=types.Blob(data=data, mime_type=media_type)))
        elif kind == "tool-result":
            output = part.get("output")
            body = tool_output_text(output)
            out.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=str(part.get("toolName", "")),
                        response={"error": body} if tool_output_is_error(output) else {"output": body},
                    )
                )
            )
    return out


def _model_parts(parts: list[dict[str, Any]]) -> list[types.Part]:
    out: list[types.Part] = []
    for part in parts:
        kind = part.get("type")
        if kind == "text":
            text = str(part.get("text", ""))
            if text:
                out.append(types.Part(text=text))
        elif kind == "tool-call":
            options = cast("dict[str, Any]", part.get("providerOptions") or {})
            signature = cast("dict[str, Any]", options.get("google") or {}).get("thoughtSignature")
            out.append(
                types.Part(
                    function_call=types.FunctionCall(
                        name=str(part.get("toolName", "")), args=part.get("input") or {}
                    ),
                    thought_signature=base64.b64decode(signature) if isinstance(signature, str) else None,
                )
            )
    return out


def provider_error_from(exc: Exception) -> ProviderCallError:
    if isinstance(exc, genai_errors.APIError):
        error = ProviderCallError(str(exc.message or exc.status or "provider error"), status_code=exc.code)
    elif isinstance(exc, TimeoutError):
        error = ProviderCallError("request timed out", is_retryable=True)
    else:
        raise exc
    error.__cause__ = exc
    return error


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


_FINISH = {"STOP": "stop", "MAX_TOKENS": "length", "SAFETY": "content-filter", "RECITATION": "content-filter"}


class GeminiModel:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        client: Any | None = None,
    ) -> None:
        self._model = model
        if client is not None:
            self._client: Any = client
            return
        http_options = types.HttpOptions(base_url=base_url_cho_google(base_url), headers=headers or None)
        self._client = genai.Client(api_key=api_key, http_options=http_options)

    @property
    def model_id(self) -> str:
        return self._model

    async def complete(self, request: ModelRequest) -> ModelCompletion:
        contents, warnings = to_gemini_contents(request.messages)
        config_args: dict[str, Any] = {}
        if request.system:
            config_args["system_instruction"] = request.system
        if request.tools:
            config_args["tools"] = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name, description=t.description, parameters_json_schema=dict(t.parameters)
                        )
                        for t in request.tools
                    ]
                )
            ]
            # The loop owns the tool cycle: no SDK-side automatic function calling.
            config_args["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        if request.max_output_tokens:
            config_args["max_output_tokens"] = request.max_output_tokens
        google_options = (request.provider_options or {}).get("google", {})
        level = google_options.get("thinkingConfig", {}).get("thinkingLevel")
        if isinstance(level, str):
            config_args["thinking_config"] = types.ThinkingConfig(
                thinking_level=level,  # type: ignore[arg-type]  # the enum accepts its lowercase value
                include_thoughts=True,
            )
        if request.headers or request.timeout_s:
            config_args["http_options"] = types.HttpOptions(
                headers=request.headers or None,
                timeout=int(request.timeout_s * 1000) if request.timeout_s else None,
            )
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model, contents=contents, config=types.GenerateContentConfig(**config_args)
            )
            return await _aggregate(stream, self._model, warnings)
        except (genai_errors.APIError, TimeoutError) as exc:
            raise provider_error_from(exc) from exc


async def _aggregate(stream: Any, requested_model: str, warnings: list[str]) -> ModelCompletion:
    text: list[str] = []
    reasoning: list[str] = []
    tool_calls: list[ToolCallPart] = []
    finish = ""
    usage = ModelUsage()
    model_id: str | None = None
    chunk: Any
    async for chunk in stream:
        model_id = getattr(chunk, "model_version", None) or model_id
        raw_usage = getattr(chunk, "usage_metadata", None)
        if raw_usage is not None:
            usage = _usage_of(raw_usage)
        for candidate in list(getattr(chunk, "candidates", None) or []):
            reason = getattr(candidate, "finish_reason", None)
            if reason is not None:
                finish = str(getattr(reason, "name", reason) or "")
            content = getattr(candidate, "content", None)
            for part in list(getattr(content, "parts", None) or []):
                call = getattr(part, "function_call", None)
                if call is not None:
                    signature = getattr(part, "thought_signature", None)
                    args = getattr(call, "args", None)
                    tool_calls.append(
                        ToolCallPart(
                            tool_call_id=str(getattr(call, "id", None) or f"call-{len(tool_calls)}"),
                            tool_name=str(getattr(call, "name", "")),
                            input=dict(cast("dict[str, Any]", args)) if isinstance(args, dict) else {},
                            provider_options=(
                                {"google": {"thoughtSignature": base64.b64encode(signature).decode()}}
                                if isinstance(signature, bytes)
                                else None
                            ),
                        )
                    )
                elif getattr(part, "text", None):
                    (reasoning if getattr(part, "thought", False) else text).append(str(part.text))
    finish_reason = "tool-calls" if tool_calls else _FINISH.get(finish.upper(), finish.lower() or "stop")
    return ModelCompletion(
        text="".join(text),
        reasoning_text="".join(reasoning),
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        usage=usage,
        warnings=list(warnings),
        model_id=model_id or requested_model,
    )


def _usage_of(raw: Any) -> ModelUsage:
    prompt = _int_or_none(getattr(raw, "prompt_token_count", None))
    output = _int_or_none(getattr(raw, "response_token_count", None))
    if output is None:
        output = _int_or_none(getattr(raw, "candidates_token_count", None))
    thoughts = _int_or_none(getattr(raw, "thoughts_token_count", None))
    total = _int_or_none(getattr(raw, "total_token_count", None))
    return ModelUsage(
        input_tokens=prompt,
        output_tokens=None if output is None and thoughts is None else (output or 0) + (thoughts or 0),
        total_tokens=total,
        reasoning_tokens=thoughts,
        cache_read_tokens=_int_or_none(getattr(raw, "cached_content_token_count", None)),
    )
