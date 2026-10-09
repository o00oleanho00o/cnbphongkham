"""Profiles, the model factory and the chat CLI (run with the echo model)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agent_app.assembly import build_agent, build_prompt
from agent_app.cli import ConsoleObserver, main, stats_line
from agent_app.model_factory import build_model, describe_model, resolve_model_config, resolve_model_settings
from agent_app.profile import Profile, load_profile
from agentcore import ModelConfigError, ToolResultBlock, ToolUseBlock, TurnResult, Usage
from agentcore.harness.model.anthropic import AnthropicModel
from agentcore.harness.model.scripted import EchoModel
from agentcore.harness.tools.builtin import builtin_tools
from agentcore.prompt import CONTEXT_EXPLAINER

DEV_PROFILE = Path(__file__).resolve().parents[1] / "agents" / "dev"


def _profile(**model: str) -> Profile:
    return Profile.model_validate(
        {"agent": {"name": "t", "system_prompt": "p"}, "model": {"model": "from-profile", **model}}
    )


def test_the_dev_profile_loads_and_its_tools_exist() -> None:
    profile = load_profile(DEV_PROFILE)

    assert profile.agent.name == "dev"
    assert builtin_tools(timezone=profile.agent.timezone).subset(profile.agent.tools).names() == [
        "get_datetime"
    ]
    assert profile.loop_policy().max_steps == profile.loop.max_steps


def test_compaction_is_on_only_with_a_context_window() -> None:
    dev = load_profile(DEV_PROFILE).context_policy()

    assert dev is not None
    assert (dev.window_tokens, dev.compact_at, dev.keep_recent_ratio) == (128_000, 0.75, 0.20)
    assert _profile().context_policy() is None


def test_context_and_compact_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("/compact\nmột\nhai\n/compact\n/context\n/exit\n"))

    assert main(["chat", "--profile", str(DEV_PROFILE), "--fake"]) == 0
    out = capsys.readouterr().out
    assert "nothing to compact yet\n" in out
    assert "compacted 2 messages\n" in out
    assert "context: ~" in out
    assert "compaction at ~94464 tokens (window 128000, keeps ~18892 recent)" in out
    assert "for the first 2 of 4 messages" in out


def test_without_a_window_the_commands_say_compaction_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "plain.toml"
    path.write_text('[agent]\nname = "x"\n', encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO("/context\n/compact\n/exit\n"))

    assert main(["chat", "--profile", str(path), "--fake"]) == 0
    out = capsys.readouterr().out
    assert "compaction: off" in out
    assert "compaction is off: set [context] window_tokens" in out


def test_the_dev_agent_folder_gives_persona_rules_tools_and_a_bundled_skill() -> None:
    profile = load_profile(DEV_PROFILE)

    agent = build_agent(profile, fake=True, env={})

    assert profile.agent.system_prompt.startswith("You are a helpful general-purpose assistant.")
    assert profile.agent.rules.startswith("## How you work")
    assert agent.tools.names() == [
        "get_datetime",
        "memory",
        "skill_list",
        "skill_view",
        "skill_write",
        "skill_patch",
    ]
    system = agent.prompt.render_system()
    assert system.startswith(profile.agent.system_prompt.strip())
    assert "## How you work" in system
    assert "## Memory" in system


async def test_the_bundled_skill_is_listed_and_read_only() -> None:
    agent = build_agent(load_profile(DEV_PROFILE), fake=True, env={})
    assert agent.skills is not None

    (skill,) = await agent.skills.list("default", "dev")

    assert (skill.name, skill.origin) == ("write-a-plan", "bundled")
    with pytest.raises(ValueError, match="bundled skill"):
        await agent.skills.write("default", "dev", name="write-a-plan", description="x", body="y")


def test_a_persona_in_soul_md_and_in_the_profile_is_refused(tmp_path: Path) -> None:
    (tmp_path / "agent.toml").write_text('[agent]\nname = "x"\nsystem_prompt = "p"\n', encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("soul", encoding="utf-8")

    with pytest.raises(ValueError, match="not both"):
        load_profile(tmp_path)


def test_a_plain_toml_profile_needs_no_folder_files(tmp_path: Path) -> None:
    path = tmp_path / "plain.toml"
    path.write_text('[agent]\nname = "x"\nsystem_prompt = "p"\n', encoding="utf-8")

    profile = load_profile(path)

    assert (profile.agent.system_prompt, profile.agent.rules, profile.folder) == ("p", "", tmp_path)
    assert build_prompt(profile, tool_names=[]).render_system() == f"p\n\n{CONTEXT_EXPLAINER}"


def test_an_unknown_prompt_section_stops_the_chat(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.toml"
    path.write_text('[agent]\nname = "x"\n\n[prompt]\nsections = ["identity", "nope"]\n', encoding="utf-8")

    assert main(["chat", "--profile", str(path), "--fake"]) == 2
    assert "Unknown prompt section(s): nope" in capsys.readouterr().out


def test_the_prompt_command_shows_the_system_prompt_and_the_context_block(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("/prompt\n/exit\n"))

    assert main(["chat", "--profile", str(DEV_PROFILE), "--fake"]) == 0
    out = capsys.readouterr().out
    assert (
        "--- system prompt (frozen for this session) ---\nYou are a helpful general-purpose assistant." in out
    )
    assert "<agent-context>\nCurrent time: " in out
    assert "Channel: cli\nStep 1 of 6.\n</agent-context>" in out


def test_a_misspelt_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text('[agent]\nname = "x"\nsystem_prompt = "p"\ntool = ["get_datetime"]\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        load_profile(path)


def test_the_environment_overrides_the_profile_and_holds_the_key() -> None:
    env = {"LLM_MODEL": "from-env", "LLM_BASE_URL": "https://llm.test/v1", "LLM_API_KEY": "secret"}

    config = resolve_model_config(_profile(base_url="https://profile.test/v1"), env)

    assert (config.model, config.base_url, config.api_key) == ("from-env", "https://llm.test/v1", "secret")


def test_without_overrides_the_profile_values_are_used() -> None:
    config = resolve_model_config(_profile(base_url="https://profile.test/v1"), {"LLM_API_KEY": "k"})

    assert (config.model, config.base_url) == ("from-profile", "https://profile.test/v1")
    assert describe_model(_profile(), fake=False, env={"LLM_API_KEY": "k"}) == (
        "from-profile via api.openai.com (openai-compatible)"
    )


def test_provider_and_reasoning_come_from_the_profile_or_the_environment() -> None:
    profile = Profile.model_validate(
        {"agent": {"name": "t"}, "model": {"model": "m", "provider": "anthropic", "reasoning": "low"}}
    )

    from_profile = resolve_model_settings(profile, {})
    from_env = resolve_model_settings(profile, {"LLM_PROVIDER": "openai-compatible", "LLM_REASONING": "off"})

    assert (from_profile.provider, from_profile.reasoning) == ("anthropic", "low")
    assert (from_env.provider, from_env.reasoning) == ("openai-compatible", "off")
    assert describe_model(profile, fake=False, env={}) == "m via api.anthropic.com (anthropic, reasoning low)"
    with pytest.raises(ValueError, match="LLM_REASONING='max'"):
        resolve_model_settings(profile, {"LLM_REASONING": "max"})


def test_the_anthropic_provider_builds_the_anthropic_adapter() -> None:
    profile = Profile.model_validate(
        {"agent": {"name": "t"}, "model": {"model": "m", "provider": "anthropic"}}
    )

    assert isinstance(build_model(profile, fake=False, env={"LLM_API_KEY": "k"}), AnthropicModel)
    with pytest.raises(ModelConfigError):
        build_model(profile, fake=False, env={})


def test_the_loop_policy_carries_the_reasoning_effort() -> None:
    profile = Profile.model_validate({"agent": {"name": "t"}, "model": {"model": "m", "reasoning": "high"}})

    assert profile.loop_policy().reasoning == "high"
    assert profile.loop_policy(reasoning="off").reasoning == "off"
    agent = build_agent(profile, fake=False, env={"LLM_API_KEY": "k", "LLM_REASONING": "low"})
    assert agent.policy.reasoning == "low"


def test_the_guards_section_picks_the_hooks_and_the_tool_limits() -> None:
    dev = build_agent(load_profile(DEV_PROFILE), fake=True, env={})
    profile = Profile.model_validate(
        {
            "agent": {"name": "t"},
            "guards": {
                "injection_scan": False,
                "warn_tool_results": False,
                "max_parallel_tools": 2,
                "max_tool_calls_per_step": 3,
            },
        }
    )

    agent = build_agent(profile, fake=True, env={})

    assert [h.name for h in dev.hooks.pre_tool] == ["injection_guard"]
    assert [h.name for h in dev.hooks.post_tool] == ["secret_redactor", "result_warning"]
    assert (agent.hooks.pre_tool, [h.name for h in agent.hooks.post_tool]) == ([], ["secret_redactor"])
    assert (agent.policy.max_parallel_tools, agent.policy.max_tool_calls_per_step) == (2, 3)
    with pytest.raises(ValidationError):
        Profile.model_validate({"agent": {"name": "t"}, "guards": {"max_parallel_tools": 0}})


def test_a_missing_key_is_a_config_error_and_fake_needs_no_key() -> None:
    with pytest.raises(ModelConfigError) as caught:
        build_model(_profile(), fake=False, env={})

    assert caught.value.field == "api_key"
    assert isinstance(build_model(_profile(), fake=True, env={}), EchoModel)


def _result(**kwargs: Any) -> TurnResult:
    fields: dict[str, Any] = {
        "text": "14:00",
        "stop": "completed",
        "steps": 2,
        "usage": Usage(input_tokens=30, output_tokens=5),
        "new_messages": [],
        "duration_s": 1.25,
        **kwargs,
    }
    return TurnResult(**fields)


def test_the_console_prints_the_turn_as_it_happens(capsys: pytest.CaptureFixture[str]) -> None:
    observer = ConsoleObserver()

    observer.thinking("hmm")
    observer.thinking(" more")
    observer.text("Để tôi")
    observer.text(" xem")
    observer.tool_call(ToolUseBlock(id="c1", name="get_datetime", args={}))
    observer.tool_result(ToolResultBlock(tool_use_id="c1", name="get_datetime", content="14:00"))
    observer.text("14:00")
    tail = observer.finish(_result())

    assert capsys.readouterr().out + tail == (
        "  (thinking...)\n"
        "agent> Để tôi xem\n"
        "  [tool] get_datetime({})\n"
        "  [tool] get_datetime -> ok: 14:00\n"
        "agent> 14:00\n"
        "  (steps=2, 1.2s, in=30, out=5, stop=completed)\n"
    )


def test_a_reply_that_did_not_stream_is_printed_at_the_end() -> None:
    assert (
        ConsoleObserver().finish(_result())
        == "agent> 14:00\n  (steps=2, 1.2s, in=30, out=5, stop=completed)\n"
    )


def test_the_stats_show_cache_reasoning_and_compactions_only_when_present() -> None:
    usage = Usage(input_tokens=30, output_tokens=5, cache_read_tokens=20, reasoning_tokens=3)

    assert stats_line(_result(usage=usage, compactions=1)) == (
        "  (steps=2, 1.2s, in=30, out=5, cached=20, reasoning=3, stop=completed, compactions=1)"
    )


def test_chat_with_the_echo_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("xin chào\n/new\n/exit\n"))

    exit_code = main(["chat", "--profile", str(DEV_PROFILE), "--fake"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "agent> (echo) xin chào\n  (steps=1" in out
    assert "new session: cli-" in out


def test_chat_ends_at_the_end_of_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("hello\n"))

    assert main(["chat", "--profile", str(DEV_PROFILE), "--fake"]) == 0
    assert "agent> (echo) hello" in capsys.readouterr().out


def test_piped_utf8_input_is_read_as_utf8_whatever_the_code_page(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A Windows pipe opens stdin in the legacy code page while the bytes are UTF-8.
    piped = io.TextIOWrapper(io.BytesIO("xin chào\n/exit\n".encode()), encoding="cp1252")
    monkeypatch.setattr("sys.stdin", piped)

    assert main(["chat", "--profile", str(DEV_PROFILE), "--fake"]) == 0
    assert "agent> (echo) xin chào" in capsys.readouterr().out


def test_chat_with_a_missing_profile_exits_with_a_config_error(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["chat", "--profile", "does-not-exist.toml", "--fake"])

    assert exit_code == 2
    assert capsys.readouterr().out.startswith("error:")
