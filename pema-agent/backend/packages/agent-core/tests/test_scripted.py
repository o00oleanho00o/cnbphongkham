"""The provider-free models used by tests and by ``agent chat --fake``."""

from __future__ import annotations

import pytest

from agentcore import LlmRequest, Message
from agentcore.harness.model.scripted import EchoModel, ScriptedModel, reply


async def test_the_echo_model_repeats_the_last_user_message() -> None:
    request = LlmRequest(system="", messages=[Message.user("first"), Message.user("xin chào")])

    result = await EchoModel().complete(request)

    assert result.message.text() == "(echo) xin chào"


async def test_a_scripted_model_records_requests_and_fails_when_its_script_runs_out() -> None:
    model = ScriptedModel([reply("one")])
    request = LlmRequest(system="s", messages=[Message.user("hi")])

    assert (await model.complete(request)).message.text() == "one"
    with pytest.raises(RuntimeError, match="no step left"):
        await model.complete(request)
    assert len(model.requests) == 2
