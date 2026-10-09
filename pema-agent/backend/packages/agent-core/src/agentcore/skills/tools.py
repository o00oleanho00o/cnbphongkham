"""``skill_list``, ``skill_view``, ``skill_write``, ``skill_patch``: the agent reads and keeps its skills."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentcore.harness.tools.spec import ToolContext, ToolOutput, ToolSpec
from agentcore.skills.library import MAX_BODY_CHARS, SkillError, SkillLibrary

SKILL_TOOL_NAMES = ("skill_list", "skill_view", "skill_write", "skill_patch")


class NoArgs(BaseModel):
    pass


class ViewArgs(BaseModel):
    name: str


class WriteArgs(BaseModel):
    name: str = Field(description="lowercase, e.g. 'monthly-report'; letters, digits, '.', '_', '-'")
    description: str = Field(description="One line: when to use this skill.")
    body: str = Field(description="The instructions, in Markdown.")


class PatchArgs(BaseModel):
    name: str
    old_text: str = Field(description="Text that appears exactly once in the skill body.")
    new_text: str


def skill_tools(library: SkillLibrary, *, agent: str) -> list[ToolSpec[Any]]:
    async def list_skills(args: NoArgs, ctx: ToolContext) -> ToolOutput:
        skills = await library.list(ctx.tenant_id, agent)
        if not skills:
            return ToolOutput(text="No skills yet.")
        return ToolOutput(text="\n".join(f"- {s.name} ({s.origin}): {s.description}" for s in skills))

    async def view(args: ViewArgs, ctx: ToolContext) -> ToolOutput:
        skill = await library.get(ctx.tenant_id, agent, args.name)
        if skill is None:
            return ToolOutput(text=f"No skill named {args.name!r}; see skill_list.", is_error=True)
        return ToolOutput(text=f"# {skill.name}\n{skill.description}\n\n{skill.body}")

    async def write(args: WriteArgs, ctx: ToolContext) -> ToolOutput:
        try:
            skill = await library.write(
                ctx.tenant_id, agent, name=args.name, description=args.description, body=args.body
            )
        except SkillError as err:
            return ToolOutput(text=str(err), is_error=True)
        return ToolOutput(
            text=f"Saved skill {skill.name!r} ({len(skill.body)} chars). skill_view shows it now; the skills "
            "index in your prompt lists it from the next session."
        )

    async def patch(args: PatchArgs, ctx: ToolContext) -> ToolOutput:
        try:
            skill = await library.patch(
                ctx.tenant_id, agent, name=args.name, old_text=args.old_text, new_text=args.new_text
            )
        except SkillError as err:
            return ToolOutput(text=str(err), is_error=True)
        return ToolOutput(text=f"Patched skill {skill.name!r} ({len(skill.body)} chars).")

    specs: list[ToolSpec[Any]] = [
        ToolSpec(
            name="skill_list", description="List the skills you have.", args_model=NoArgs, handler=list_skills
        ),
        ToolSpec(
            name="skill_view",
            description="Read a skill's full instructions before doing a task it covers.",
            args_model=ViewArgs,
            handler=view,
            max_result_chars=MAX_BODY_CHARS + 2_000,
        ),
        ToolSpec(
            name="skill_write",
            description="Create or overwrite one of your skills: reusable instructions for a recurring task.",
            args_model=WriteArgs,
            handler=write,
        ),
        ToolSpec(
            name="skill_patch",
            description="Change part of one of your skills by replacing text that appears exactly once.",
            args_model=PatchArgs,
            handler=patch,
        ),
    ]
    return specs
