"""Skills: named instructions for recurring tasks, stored as ``SKILL.md`` text.

A skill is either bundled (written by people, shipped in the agent's folder, read-only) or written by the
agent through the skill tools (kept in a ``SkillStore``). A bundled name can never be taken by an agent skill.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Literal, Protocol

SKILL_FILE: Final = "SKILL.md"
NAME_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
MAX_DESCRIPTION_CHARS: Final = 1_024
MAX_BODY_CHARS: Final = 20_000
MAX_AGENT_SKILLS: Final = 100

SkillOrigin = Literal["bundled", "agent"]


class SkillError(ValueError):
    """A skill is invalid or a change cannot be made; the message tells the agent what to fix."""


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    body: str
    origin: SkillOrigin = "agent"

    def __post_init__(self) -> None:
        if not NAME_PATTERN.fullmatch(self.name):
            raise SkillError(
                f"Invalid skill name {self.name!r}: 1-64 of a-z, 0-9, '.', '_', '-', "
                "starting with a letter or digit."
            )
        if not self.description.strip() or "\n" in self.description:
            raise SkillError("The description must be one non-empty line.")
        if len(self.description) > MAX_DESCRIPTION_CHARS:
            raise SkillError(f"The description is longer than {MAX_DESCRIPTION_CHARS} chars.")
        if not self.body.strip():
            raise SkillError("The skill body is empty.")
        if len(self.body) > MAX_BODY_CHARS:
            raise SkillError(f"The skill body has {len(self.body)} chars; the limit is {MAX_BODY_CHARS}.")

    def to_markdown(self) -> str:
        return f"---\nname: {self.name}\ndescription: {self.description}\n---\n\n{self.body.strip()}\n"


def parse_skill_markdown(text: str, *, origin: SkillOrigin = "agent") -> Skill:
    """``---`` frontmatter with ``name`` and ``description``, then the body."""
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillError("A skill starts with a '---' frontmatter block.")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise SkillError("The frontmatter block is not closed with '---'.")
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return Skill(
        name=fields.get("name", ""),
        description=fields.get("description", ""),
        body="\n".join(lines[end + 1 :]).strip(),
        origin=origin,
    )


def load_bundled_skills(directory: Path) -> list[Skill]:
    """``<directory>/<name>/SKILL.md`` for each skill; the folder name must equal the skill name."""
    if not directory.is_dir():
        return []
    skills: list[Skill] = []
    for folder in sorted(p for p in directory.iterdir() if p.is_dir()):
        path = folder / SKILL_FILE
        if not path.is_file():
            continue
        skill = parse_skill_markdown(path.read_text(encoding="utf-8"), origin="bundled")
        if skill.name != folder.name:
            raise SkillError(f"{path}: name {skill.name!r} does not match its folder {folder.name!r}")
        skills.append(skill)
    return skills


class SkillStore(Protocol):
    """Where the agent's own skills are kept."""

    async def list(self, tenant_id: str, agent: str) -> list[Skill]: ...

    async def get(self, tenant_id: str, agent: str, name: str) -> Skill | None: ...

    async def put(self, tenant_id: str, agent: str, skill: Skill) -> None: ...


class InMemorySkillStore:
    def __init__(self) -> None:
        self._skills: dict[tuple[str, str], dict[str, Skill]] = {}

    async def list(self, tenant_id: str, agent: str) -> list[Skill]:
        return sorted(self._skills.get((tenant_id, agent), {}).values(), key=lambda s: s.name)

    async def get(self, tenant_id: str, agent: str, name: str) -> Skill | None:
        return self._skills.get((tenant_id, agent), {}).get(name)

    async def put(self, tenant_id: str, agent: str, skill: Skill) -> None:
        self._skills.setdefault((tenant_id, agent), {})[skill.name] = skill


class SkillLibrary:
    def __init__(
        self, store: SkillStore, bundled: Sequence[Skill] = (), *, max_agent_skills: int = MAX_AGENT_SKILLS
    ) -> None:
        self._store = store
        self._bundled = {skill.name: skill for skill in bundled}
        self._max_agent_skills = max_agent_skills

    async def list(self, tenant_id: str, agent: str) -> list[Skill]:
        """Bundled skills first, then the agent's own."""
        own = [s for s in await self._store.list(tenant_id, agent) if s.name not in self._bundled]
        return [*self._bundled.values(), *own]

    async def get(self, tenant_id: str, agent: str, name: str) -> Skill | None:
        return self._bundled.get(name) or await self._store.get(tenant_id, agent, name)

    async def write(self, tenant_id: str, agent: str, *, name: str, description: str, body: str) -> Skill:
        self._refuse_bundled(name)
        skill = Skill(name=name, description=description.strip(), body=body.strip())
        is_new = await self._store.get(tenant_id, agent, name) is None
        if is_new and len(await self._store.list(tenant_id, agent)) >= self._max_agent_skills:
            raise SkillError(f"There are already {self._max_agent_skills} skills; improve an existing one.")
        await self._store.put(tenant_id, agent, skill)
        return skill

    async def patch(self, tenant_id: str, agent: str, *, name: str, old_text: str, new_text: str) -> Skill:
        self._refuse_bundled(name)
        current = await self._store.get(tenant_id, agent, name)
        if current is None:
            raise SkillError(f"No skill named {name!r}; create it with skill_write.")
        count = current.body.count(old_text) if old_text else 0
        if count != 1:
            found = "is not in" if count == 0 else f"appears {count} times in"
            raise SkillError(f"old_text {found} the skill body; give text that appears exactly once.")
        patched = replace(current, body=current.body.replace(old_text, new_text).strip())
        await self._store.put(tenant_id, agent, patched)
        return patched

    def _refuse_bundled(self, name: str) -> None:
        if name in self._bundled:
            raise SkillError(
                f"{name!r} is a bundled skill and cannot be changed by the agent; use another name."
            )
