"""Skills: SKILL.md parsing, bundled skills, the library rules, the skill tools and the skills index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentcore import PromptBuilder, PromptEnv, ToolContext, ToolRegistry, builtin_sections
from agentcore.memory.tool import STORAGE_TOOL_TIMEOUT_S
from agentcore.prompt import SessionData, SkillEntry
from agentcore.prompt.builtin import SKILLS_SHOWN
from agentcore.skills import (
    MAX_BODY_CHARS,
    InMemorySkillStore,
    Skill,
    SkillError,
    SkillLibrary,
    load_bundled_skills,
    parse_skill_markdown,
    skill_tools,
)

PLAN = Skill(name="write-a-plan", description="Plan first.", body="1. Goal\n2. Steps", origin="bundled")
CTX = ToolContext(session_id="s", tenant_id="t")


def test_a_skill_round_trips_through_markdown() -> None:
    text = PLAN.to_markdown()

    assert text == "---\nname: write-a-plan\ndescription: Plan first.\n---\n\n1. Goal\n2. Steps\n"
    assert parse_skill_markdown(text, origin="bundled") == PLAN


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "Bad Name"}, "Invalid skill name"),
        ({"name": "-x"}, "Invalid skill name"),
        ({"description": "two\nlines"}, "one non-empty line"),
        ({"description": "x" * 1_025}, "longer than 1024"),
        ({"body": " "}, "body is empty"),
        ({"body": "x" * (MAX_BODY_CHARS + 1)}, "the limit is"),
    ],
)
def test_invalid_skills_are_refused(kwargs: dict[str, Any], message: str) -> None:
    fields: dict[str, Any] = {"name": "ok", "description": "d", "body": "b", **kwargs}

    with pytest.raises(SkillError, match=message):
        Skill(**fields)


@pytest.mark.parametrize(
    ("text", "message"), [("no frontmatter", "starts with"), ("---\nname: x\n", "not closed")]
)
def test_broken_frontmatter_is_refused(text: str, message: str) -> None:
    with pytest.raises(SkillError, match=message):
        parse_skill_markdown(text)


def test_bundled_skills_load_from_their_folders(tmp_path: Path) -> None:
    (tmp_path / "write-a-plan").mkdir()
    (tmp_path / "write-a-plan" / "SKILL.md").write_text(PLAN.to_markdown(), encoding="utf-8")
    (tmp_path / "empty-folder").mkdir()

    assert load_bundled_skills(tmp_path) == [PLAN]
    assert load_bundled_skills(tmp_path / "missing") == []


def test_a_bundled_skill_must_match_its_folder(tmp_path: Path) -> None:
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "SKILL.md").write_text(PLAN.to_markdown(), encoding="utf-8")

    with pytest.raises(SkillError, match="does not match its folder"):
        load_bundled_skills(tmp_path)


async def test_the_library_lists_bundled_first_and_keeps_them_read_only() -> None:
    library = SkillLibrary(InMemorySkillStore(), [PLAN])
    await library.write("t", "dev", name="reply-style", description="How to reply.", body="Be brief.")

    assert [(s.name, s.origin) for s in await library.list("t", "dev")] == [
        ("write-a-plan", "bundled"),
        ("reply-style", "agent"),
    ]
    assert await library.list("other-tenant", "dev") == [PLAN]
    with pytest.raises(SkillError, match="bundled skill"):
        await library.write("t", "dev", name="write-a-plan", description="d", body="b")
    with pytest.raises(SkillError, match="bundled skill"):
        await library.patch("t", "dev", name="write-a-plan", old_text="Goal", new_text="Aim")


async def test_the_number_of_agent_skills_is_capped_but_overwriting_is_allowed() -> None:
    library = SkillLibrary(InMemorySkillStore(), max_agent_skills=1)
    await library.write("t", "dev", name="one", description="d", body="b")

    await library.write("t", "dev", name="one", description="d2", body="b2")
    with pytest.raises(SkillError, match="already 1 skills"):
        await library.write("t", "dev", name="two", description="d", body="b")


async def test_a_patch_needs_text_that_appears_exactly_once() -> None:
    library = SkillLibrary(InMemorySkillStore())
    await library.write("t", "dev", name="s", description="d", body="step one\nstep two")

    patched = await library.patch("t", "dev", name="s", old_text="two", new_text="2")

    assert patched.body == "step one\nstep 2"
    with pytest.raises(SkillError, match="appears 2 times"):
        await library.patch("t", "dev", name="s", old_text="step", new_text="x")
    with pytest.raises(SkillError, match="is not in"):
        await library.patch("t", "dev", name="s", old_text="three", new_text="x")
    with pytest.raises(SkillError, match="No skill named"):
        await library.patch("t", "dev", name="nope", old_text="a", new_text="b")


async def _call(tools: ToolRegistry, tool: str, /, **args: str) -> tuple[str, bool]:
    spec = tools.get(tool)
    assert spec is not None
    output = await spec.handler(spec.args_model.model_validate(args), CTX)
    return output.text, output.is_error


async def test_the_skill_tools_list_view_write_and_patch() -> None:
    tools = ToolRegistry(skill_tools(SkillLibrary(InMemorySkillStore(), [PLAN]), agent="dev"))

    written = await _call(
        tools, "skill_write", name="reply-style", description="How to reply.", body="Be brief."
    )
    patched = await _call(tools, "skill_patch", name="reply-style", old_text="brief", new_text="kind")
    listed = await _call(tools, "skill_list")
    viewed = await _call(tools, "skill_view", name="reply-style")

    assert written[0].startswith("Saved skill 'reply-style'")
    assert patched == ("Patched skill 'reply-style' (8 chars).", False)
    assert listed == (
        "- write-a-plan (bundled): Plan first.\n- reply-style (agent): How to reply.",
        False,
    )
    assert viewed == ("# reply-style\nHow to reply.\n\nBe kind.", False)


def test_the_skill_tools_wait_longer_than_the_default_for_their_storage() -> None:
    tools = skill_tools(SkillLibrary(InMemorySkillStore()), agent="dev")

    assert {spec.timeout_s for spec in tools} == {STORAGE_TOOL_TIMEOUT_S}


async def test_the_skill_tools_turn_mistakes_into_error_results() -> None:
    tools = ToolRegistry(skill_tools(SkillLibrary(InMemorySkillStore()), agent="dev"))

    assert await _call(tools, "skill_list") == ("No skills yet.", False)
    assert (await _call(tools, "skill_view", name="nope"))[1]
    bad = await _call(tools, "skill_write", name="Bad Name", description="d", body="b")
    assert bad[1]
    assert "Invalid skill name" in bad[0]


def _skills_section(env: PromptEnv, data: SessionData) -> str:
    return PromptBuilder(env, builtin_sections().select(["skills"])).render_system(data)


def test_the_skills_index_lists_names_and_caps_its_length() -> None:
    many = tuple(SkillEntry(f"s{i}", "d") for i in range(SKILLS_SHOWN + 5))
    reader = PromptEnv(agent_name="dev", persona="")
    writer = PromptEnv(agent_name="dev", persona="", tool_names=("skill_write",))

    index = _skills_section(reader, SessionData(skills=many))

    assert index.startswith("## Skills\nBefore a task a skill covers, read it with skill_view")
    assert "- s0: d" in index
    assert f"- s{SKILLS_SHOWN}: d" not in index
    assert index.endswith("- … and 5 more (see skill_list)")
    assert _skills_section(reader, SessionData()) == ""
    assert _skills_section(writer, SessionData()).endswith("No skills yet.")
