"""The Node bridge's supervisor with a fake command runner: installing (checks, copy, pnpm, cleanup on failure),
running only while wanted, restarting after a crash, a minimal environment, uninstalling."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from plugins.zalo.personal.client import BridgeClient
from plugins.zalo.personal.supervisor import SOURCE, BridgeSupervisor


class FakeProcess:
    def __init__(self) -> None:
        self.code: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = 0

    def kill(self) -> None:
        self.code = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.code or 0


class FakeRunner:
    def __init__(
        self, *, node: str | None = "node", node_version: str = "v24.1.0", pnpm_code: int = 0
    ) -> None:
        self._node = node
        self._version = node_version
        self._pnpm_code = pnpm_code
        self.commands: list[list[str]] = []
        self.spawned: list[tuple[list[str], Path, dict[str, str]]] = []
        self.processes: list[FakeProcess] = []

    def which(self, program: str) -> str | None:
        return self._node if program == "node" else "pnpm"

    def run(self, args: list[str], cwd: Path, timeout_s: float) -> tuple[int, str]:
        self.commands.append(args)
        if args[-1] == "--version":
            return 0, self._version
        return self._pnpm_code, "Packages: +120\nDone in 3s"

    def spawn(self, args: list[str], cwd: Path, env: Mapping[str, str], log: Path) -> FakeProcess:
        self.spawned.append((args, cwd, dict(env)))
        process = FakeProcess()
        self.processes.append(process)
        return process


def _healthy(base_url: str, secret: str) -> BridgeClient:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    return BridgeClient(base_url, secret, transport=transport)


def _supervisor(tmp_path: Path, runner: FakeRunner, **kwargs: Any) -> BridgeSupervisor:
    return BridgeSupervisor(
        lambda: tmp_path,
        self_url=lambda: "http://127.0.0.1:8080",
        runner=runner,
        client_factory=_healthy,
        **kwargs,
    )


async def test_install_copies_the_sources_and_installs_their_packages(tmp_path: Path) -> None:
    runner = FakeRunner()
    supervisor = _supervisor(tmp_path, runner)
    before = supervisor.status()

    after = await supervisor.install()

    version = json.loads((SOURCE / "package.json").read_text(encoding="utf-8"))["version"]
    folder = tmp_path / "bridge" / version
    assert (before.installed, after.installed, after.version) == (False, True, version)
    assert runner.commands[-1] == ["pnpm", "install", "--frozen-lockfile", "--prod"]
    assert (folder / "package.json").is_file()
    assert (folder / "src" / "index.ts").is_file()
    assert not list((folder / "src").glob("*.test.ts"))
    assert after.log[-1] == "Done in 3s"


@pytest.mark.parametrize(
    ("runner", "error"),
    [
        (FakeRunner(node=None), "Node.js 22.13+"),
        (FakeRunner(node_version="v20.11.0"), "22.13"),
        (FakeRunner(pnpm_code=1), "pnpm install"),
    ],
)
async def test_a_failed_install_leaves_nothing_and_says_why(
    tmp_path: Path, runner: FakeRunner, error: str
) -> None:
    supervisor = _supervisor(tmp_path, runner)

    with pytest.raises(ValueError, match=error):
        await supervisor.install()

    status = supervisor.status()
    assert status.installed is False
    assert status.error is not None
    assert error in status.error
    assert not (tmp_path / "bridge").exists()


async def test_the_bridge_runs_only_while_installed_and_wanted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_SECRET_ENCRYPTION_KEY", "0f" * 32)
    monkeypatch.setenv("LLM_API_KEY", "sk-secret")
    runner = FakeRunner()
    restarted: list[int] = []
    supervisor = _supervisor(tmp_path, runner, on_restart=lambda: restarted.append(1))

    await supervisor.step(wanted=True)  # not installed yet
    not_installed = (len(runner.spawned), supervisor.client)
    await supervisor.install()
    await supervisor.step(wanted=True)
    running = supervisor.status().running
    args, cwd, env = runner.spawned[0]
    await supervisor.step(wanted=False)

    assert not_installed == (0, None)
    assert running is True
    assert args == ["node", "--import", "tsx", "src/index.ts"]
    assert cwd.parent == tmp_path / "bridge"
    assert env["PEMA_ZALO_PERSONAL_ENABLED"] == "true"
    assert env["PEMA_API_BASE_URL"] == "http://127.0.0.1:8080/v1/hooks/zalo"
    assert len(env["PEMA_ZALO_BRIDGE_SECRET"]) == 64
    assert "AGENT_SECRET_ENCRYPTION_KEY" not in env
    assert "LLM_API_KEY" not in env
    assert runner.processes[0].terminated is True
    assert (supervisor.client, supervisor.generation, restarted) == (None, 1, [1])


async def test_a_bridge_that_dies_is_started_again_after_a_pause(tmp_path: Path) -> None:
    runner = FakeRunner()
    now = [100.0]
    supervisor = _supervisor(tmp_path, runner, clock=lambda: now[0])
    await supervisor.install()
    await supervisor.step(wanted=True)
    first_secret = supervisor.secret

    runner.processes[0].code = 1
    await supervisor.step(wanted=True)
    waiting = (supervisor.client, supervisor.status().error)
    now[0] += 2.0
    await supervisor.step(wanted=True)

    assert waiting == (None, "the bridge exited with code 1")
    assert len(runner.spawned) == 2
    assert supervisor.secret not in (None, first_secret)
    assert supervisor.generation == 2
    await supervisor.stop()


async def test_uninstall_stops_the_bridge_and_removes_its_folder(tmp_path: Path) -> None:
    runner = FakeRunner()
    supervisor = _supervisor(tmp_path, runner)
    await supervisor.install()
    await supervisor.step(wanted=True)

    status = await supervisor.uninstall()

    assert (status.installed, status.running) == (False, False)
    assert runner.processes[0].terminated is True
    assert not (tmp_path / "bridge").exists()


async def test_an_external_bridge_is_always_there_and_cannot_be_installed(tmp_path: Path) -> None:
    supervisor = BridgeSupervisor(
        lambda: tmp_path, self_url=lambda: None, external=_healthy("http://bridge", "s" * 32)
    )

    with pytest.raises(ValueError, match="outside"):
        await supervisor.install()
    assert supervisor.status().to_json()["version"] == "external"
    assert supervisor.secret == "s" * 32
    job = asyncio.create_task(supervisor.keep_running(lambda: True))
    await asyncio.sleep(0.01)
    job.cancel()


def _bundled_folder(tmp_path: Path) -> Path:
    """A bridge folder as the agent's image leaves it: sources plus their installed packages."""
    folder = tmp_path / "image-bridge"
    for package in ("tsx", "zca-js"):
        (folder / "node_modules" / package).mkdir(parents=True)
    (folder / "package.json").write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")
    return folder


async def test_a_bundled_bridge_is_there_without_installing(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path / "data", FakeRunner(), bundled=_bundled_folder(tmp_path))

    status = supervisor.status()

    assert (status.installed, status.bundled, status.version) == (True, True, "0.1.0")


async def test_a_bundled_bridge_runs_from_its_own_folder_when_wanted(tmp_path: Path) -> None:
    runner = FakeRunner()
    folder = _bundled_folder(tmp_path)
    supervisor = _supervisor(tmp_path / "data", runner, bundled=folder)

    await supervisor.step(wanted=True)

    assert supervisor.status().running is True
    assert runner.spawned[0][1] == folder
    assert runner.commands == []
    await supervisor.stop()


async def test_a_bundled_bridge_cannot_be_installed_or_removed(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path / "data", FakeRunner(), bundled=_bundled_folder(tmp_path))

    with pytest.raises(ValueError, match="có sẵn"):
        await supervisor.install()
    with pytest.raises(ValueError, match="có sẵn"):
        await supervisor.uninstall()


async def test_a_bundled_folder_without_its_packages_falls_back_to_installing(tmp_path: Path) -> None:
    folder = tmp_path / "checkout-bridge"
    folder.mkdir()
    supervisor = _supervisor(tmp_path / "data", FakeRunner(), bundled=folder)

    status = await supervisor.install()

    assert (status.installed, status.bundled) == (True, False)
