"""T9 (docs/PLAN-crm-plugin.md 3.10a, rule L7): what the agent can do is a list the owner approved.

Read from the code and the files, not from a running service: every tool defined anywhere in the agent's code,
the plugins and tools of the clinic profile, the places that start a process, and what the compose file gives
the agent's container. A new tool, plugin, process or variable turns this red until the list here is changed on
purpose, with the owner's approval. Never approve a tool that reads files, runs commands or runs code.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import yaml

from agent_app.profile import load_profile

AGENT = Path(__file__).resolve().parents[1]
BACKEND = AGENT.parents[1]
CORE = BACKEND / "packages" / "agent-core" / "src" / "agentcore"
COMPOSE = BACKEND.parent / "infra" / "docker-compose.yml"
CLINIC = AGENT / "agents" / "clinic"

APPROVED_TOOLS: dict[str, str] = {
    # core
    "get_datetime": "agentcore",
    "web_search": "agentcore",
    "web_fetch": "agentcore",
    "memory": "agentcore",
    # plugins
    "kb_search": "knowledge",
    "kb_read": "knowledge",
    "scenario_search": "conversations",
    "skill_list": "skills",
    "skill_view": "skills",
    "skill_search": "skills",
    "skill_write": "skills",  # only with `agent_writes`, which the clinic profile never sets
    "skill_patch": "skills",
    "studio_list": "skills",
    "studio_view": "skills",
    "studio_save": "skills",  # saves a draft; staff press "Dùng" to make it live
}
CLINIC_PLUGINS = {"sso", "knowledge", "skills", "conversations", "jev"}
CLINIC_PROFILE_TOOLS = {"get_datetime", "memory", "web_search", "web_fetch"}
STARTS_A_PROCESS = {
    "agent_app/plugins/install.py",  # an admin installs a plugin's packages; no tool reaches it
    "plugins/zalo/personal/supervisor.py",  # runs the Zalo bridge (Node) next to the agent
}
AGENT_SERVICE_ENV = {"AGENT_DATABASE_URL"}


SKIPPED_DIRS = {"node_modules", "tests", "__pycache__", "dist", "ui"}


def _python_files() -> list[tuple[str, Path]]:
    roots = [("agentcore", CORE), ("agent_app", AGENT / "agent_app"), ("plugins", AGENT / "plugins")]
    found: list[tuple[str, Path]] = []
    for label, root in roots:
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIPPED_DIRS]  # the Zalo bridge's node_modules is huge
            found += [(label, Path(folder) / f) for f in sorted(files) if f.endswith(".py")]
    return found


def _owner(label: str, path: Path) -> str:
    if label != "plugins":
        return label
    return path.relative_to(AGENT / "plugins").parts[0]


def _tool_specs() -> dict[str, list[str]]:
    """Tool name -> where it is defined, from every ``ToolSpec(name=...)`` call."""
    found: dict[str, list[str]] = {}
    for label, path in _python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "ToolSpec"):
                continue
            name = next((k.value for k in node.keywords if k.arg == "name"), None)
            assert isinstance(name, ast.Constant), f"{path}: a ToolSpec whose name is not a literal"
            found.setdefault(str(name.value), []).append(_owner(label, path))
    return found


def test_every_tool_in_the_code_is_on_the_approved_list() -> None:
    specs = _tool_specs()
    assert {name: owners[0] for name, owners in specs.items()} == APPROVED_TOOLS
    assert all(len(owners) == 1 for owners in specs.values()), "a tool name is defined twice"


def test_the_clinic_profile_runs_the_approved_plugins_and_tools() -> None:
    profile = load_profile(CLINIC)
    assert set(profile.plugins.enabled) == CLINIC_PLUGINS
    assert set(profile.agent.tools) <= CLINIC_PROFILE_TOOLS


def test_the_clinic_agent_never_writes_its_own_skills() -> None:
    """``skill_write`` puts text into later prompts at once: a talked-into agent would keep its new rules."""
    assert load_profile(CLINIC).plugins.config("skills").get("agent_writes") is not True


def test_only_the_two_known_places_start_a_process() -> None:
    risky = ("subprocess", "os.system", "os.popen", "create_subprocess", "pty.spawn")
    found = {
        path.relative_to(CORE.parent if label == "agentcore" else AGENT).as_posix()
        for label, path in _python_files()
        if any(word in path.read_text(encoding="utf-8") for word in risky)
    }
    assert found == STARTS_A_PROCESS


def test_no_agent_code_evaluates_text_as_code() -> None:
    calls = {"eval", "exec", "compile", "__import__"}
    found = [
        f"{path.name}:{node.lineno}"
        for _, path in _python_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in calls
    ]
    assert found == []


def _agent_service() -> dict[str, Any]:
    compose: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return compose["services"]["agent"]


def test_the_agent_container_gets_only_its_own_database_and_no_port() -> None:
    """No secret of the clinic API, no key of the gateway: the agent holds no way into the CRM (rule L2)."""
    service = _agent_service()
    assert set(service.get("environment", {})) == AGENT_SERVICE_ENV
    assert "ports" not in service
