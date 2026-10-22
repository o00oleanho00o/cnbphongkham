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
    # steer the case of the chat (docs/DESIGN-case-loop.md, owner approved 2026-10-22): no network, writes
    # only agent_rt, refused outside a case's turn
    "case_done": "agentcore",
    "case_wait_until": "agentcore",
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
    # the person of the chat only, through crm-signer (owner's plan docs/PLAN-crm-plugin.md, approved 2026-10-20)
    "crm_free_slots": "crm",
    "crm_save_contact": "crm",
    "crm_book_appointment": "crm",
    "crm_my_appointments": "crm",
    "crm_confirm_appointment": "crm",
    "crm_reschedule_appointment": "crm",
    "crm_cancel_appointment": "crm",
}
CLINIC_PLUGINS = {"sso", "knowledge", "skills", "conversations", "jev", "crm", "follow_up"}
CLINIC_PROFILE_TOOLS = {"get_datetime", "memory", "web_search", "web_fetch"}
STARTS_A_PROCESS = {
    "agent_app/plugins/install.py",  # an admin installs a plugin's packages; no tool reaches it
    "plugins/zalo/personal/supervisor.py",  # runs the Zalo bridge (Node) next to the agent
}
AGENT_SERVICE_ENV = {"AGENT_DATABASE_URL", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"}
INSIDE_THE_STACK = {"localhost", "127.0.0.1", "api", "crm-signer", "postgres"}
"""What the agent reaches without the egress proxy: the Zalo bridge on loopback, the CRM's JWKS, crm-signer, its DB."""


SKIPPED_DIRS = {"node_modules", "tests", "__pycache__", "dist", "ui"}


def _python_files() -> list[tuple[str, Path]]:
    roots = [
        ("agentcore", CORE),
        ("agent_app", AGENT / "agent_app"),
        ("plugin_kit", AGENT / "plugin_kit"),
        ("plugins", AGENT / "plugins"),
    ]
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


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_the_harness_never_imports_what_plugs_into_it() -> None:
    """Agent = model + harness, everything else a plugin: the core imports neither the service nor a plugin,
    and the service imports no plugin. A plugin reaches the harness through ``ctx``, never the other way."""
    wrong = [
        f"{path.name}: {module}"
        for label, path in _python_files()
        if label != "plugins"
        for module in _imports(path)
        if module.split(".")[0] == "plugins" or (label == "agentcore" and module.split(".")[0] == "agent_app")
    ]
    assert wrong == []


def test_a_plugin_never_imports_another_plugin_and_the_kit_imports_neither_side() -> None:
    """What plugins share lives in ``plugin_kit`` (.claude/rules/agent-harness.md H1): a plugin that imports
    another breaks when that one changes or is switched off, and a kit that imported the harness or a plugin
    would not be neutral."""
    wrong = [
        f"{path.relative_to(AGENT)}: {module}"
        for label, path in _python_files()
        if label in ("plugins", "plugin_kit")
        for module in _imports(path)
        if (label == "plugin_kit" and module.split(".")[0] in ("agent_app", "plugins"))
        or (
            label == "plugins"
            and module.split(".")[0] == "plugins"
            and module.split(".")[1:2] != [_owner(label, path)]
        )
    ]
    assert wrong == []


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


def test_the_agent_goes_out_through_egress_and_reaches_the_stack_directly() -> None:
    """docs/PLAN-crm-plugin.md 3.10c, phase 1: the clients that read HTTPS_PROXY go through egress, which logs
    every destination; the stack's own services are in NO_PROXY, so a call to crm-signer never leaves it."""
    env = _agent_service()["environment"]
    assert env["HTTPS_PROXY"] == env["HTTP_PROXY"] == "http://egress:3128"
    assert set(env["NO_PROXY"].split(",")) >= INSIDE_THE_STACK
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    assert "ports" not in services["egress"]
    assert services["egress"]["read_only"] is True


def test_the_agent_container_is_read_only_and_gains_no_privilege() -> None:
    """docs/PLAN-crm-plugin.md 3.10b: talked into anything, it writes only /data and /tmp and cannot escalate."""
    service = _agent_service()
    assert service.get("read_only") is True
    assert service.get("cap_drop") == ["ALL"]
    assert "no-new-privileges:true" in service.get("security_opt", [])
    assert [t.split(":")[0] for t in service.get("tmpfs", [])] == ["/tmp"]  # noqa: S108 - a path compared
    assert service.get("volumes") == ["agent-home:/data"]
