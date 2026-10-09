"""The Node bridge on this machine: installing it (on an admin's request), running it while a personal account
needs it, and stopping it.

Installing copies the bridge's sources from the plugin folder into the plugin's data folder and runs
``pnpm install --frozen-lockfile --prod`` there (the plugin folder is never written). Nothing is installed
on its own: an admin presses Install, reads the warning (zca-js is unofficial; the account can be locked).

Running: while the bridge is installed and at least one personal account is enabled, the plugin's job keeps
one ``node`` process on a free loopback port with a fresh HMAC secret; the process gets a minimal environment
(no keys of the service). It is started again after it dies (pauses 2, 5, 30, 60 s) and stopped when no
account needs it. Its output goes to ``bridge.log`` in the data folder (the bridge never logs messages,
names, cookies or secrets).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Final, Protocol, cast

from .client import BridgeClient

SOURCE: Final = Path(__file__).resolve().parents[1] / "bridge"
COPIED: Final = ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "tsconfig.json", "src")
MIN_NODE: Final = (22, 13)
INSTALL_TIMEOUT_S: Final = 15 * 60.0
HEALTH_TIMEOUT_S: Final = 30.0
RESTART_PAUSES_S: Final = (2.0, 5.0, 30.0, 60.0)
CHECK_EVERY_S: Final = 2.0
MAX_LOG_LINES: Final = 40
PASSED_ENV: Final = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "LANG",
)
"""The only variables of the service the bridge inherits: what Node needs to run, none of the service's
keys."""

logger = logging.getLogger(__name__)


class Process(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class Runner(Protocol):
    """How commands run; tests replace it."""

    def which(self, program: str) -> str | None: ...

    def run(self, args: list[str], cwd: Path, timeout_s: float) -> tuple[int, str]: ...

    def spawn(self, args: list[str], cwd: Path, env: Mapping[str, str], log: Path) -> Process: ...


class SubprocessRunner:
    def which(self, program: str) -> str | None:
        if os.name == "nt":
            # npm-installed tools have a POSIX script next to the .cmd one; only the latter starts on Windows.
            return next((found for ext in (".exe", ".cmd") if (found := shutil.which(program + ext))), None)
        return shutil.which(program)

    def run(self, args: list[str], cwd: Path, timeout_s: float) -> tuple[int, str]:
        done = subprocess.run(  # noqa: S603 - fixed arguments, the executable resolved with which()
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
        return done.returncode, (done.stdout or "") + (done.stderr or "")

    def spawn(self, args: list[str], cwd: Path, env: Mapping[str, str], log: Path) -> Process:
        out: IO[bytes] = log.open("ab")
        try:
            return subprocess.Popen(  # noqa: S603 - fixed arguments, the executable resolved with which()
                args, cwd=cwd, env=dict(env), stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
            )
        finally:
            out.close()


@dataclass(slots=True)
class _Run:
    process: Process
    client: BridgeClient
    started: float


@dataclass(slots=True)
class BridgeStatus:
    installed: bool = False
    installing: bool = False
    version: str | None = None
    running: bool = False
    error: str | None = None
    log: list[str] = field(default_factory=list[str])

    def to_json(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "installing": self.installing,
            "version": self.version,
            "running": self.running,
            "error": self.error,
            "log": list(self.log),
        }


class BridgeSupervisor:
    def __init__(
        self,
        data_dir: Callable[[], Path],
        *,
        self_url: Callable[[], str | None],
        runner: Runner | None = None,
        on_restart: Callable[[], None] = lambda: None,
        external: BridgeClient | None = None,
        client_factory: Callable[[str, str], BridgeClient] = BridgeClient,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._data_dir = data_dir
        self._self_url = self_url
        self._runner: Runner = runner or SubprocessRunner()
        self._on_restart = on_restart
        self._external = external
        """A bridge run outside this plugin (tests, a separate container): always there, never installed."""
        self._client_factory = client_factory
        self._run: _Run | None = None
        self._installing = False
        self._error: str | None = None
        self._log: list[str] = []
        self._failures = 0
        self._retry_at = 0.0
        self.generation = 1 if external is not None else 0
        """Grows each time a new bridge process is up; channels of an older one must start again."""

    @property
    def client(self) -> BridgeClient | None:
        """The running bridge's client, None while it is not running."""
        if self._external is not None:
            return self._external
        return None if self._run is None else self._run.client

    @property
    def secret(self) -> str | None:
        client = self.client
        return None if client is None else client.secret

    def status(self) -> BridgeStatus:
        if self._external is not None:
            return BridgeStatus(installed=True, version="external", running=True)
        marker = self._marker()
        return BridgeStatus(
            installed=marker is not None,
            installing=self._installing,
            version=marker.get("version") if marker else None,
            running=self._run is not None,
            error=self._error,
            log=self._log[-MAX_LOG_LINES:],
        )

    def installed(self) -> bool:
        return self._external is not None or self._marker() is not None

    async def install(self) -> BridgeStatus:
        """Copies the sources and installs their packages; refuses a second install while one runs. Errors are
        kept in the status (and raised as ``ValueError`` for the route)."""
        if self._external is not None:
            raise ValueError("the bridge is run outside the plugin")
        if self._installing:
            raise ValueError("an install is already running")
        self._installing = True
        self._error = None
        try:
            await asyncio.to_thread(self._install)
        except ValueError as err:
            self._error = str(err)
            raise
        finally:
            self._installing = False
        return self.status()

    async def uninstall(self) -> BridgeStatus:
        if self._external is not None:
            raise ValueError("the bridge is run outside the plugin")
        await self.stop()
        await asyncio.to_thread(shutil.rmtree, self._root(), True)
        self._error = None
        self._log = []
        return self.status()

    async def keep_running(self, wanted: Callable[[], bool]) -> None:
        """The plugin's job: the bridge runs while it is installed and ``wanted()``."""
        if self._external is not None:
            await asyncio.Event().wait()
        try:
            while True:
                try:
                    await self.step(wanted())
                except Exception as err:  # the next round tries again
                    self._error = f"{type(err).__name__}: {err}"[:300]
                    logger.warning("Zalo bridge supervision failed (%s)", type(err).__name__)
                await asyncio.sleep(CHECK_EVERY_S)
        finally:
            await self.stop()

    async def stop(self) -> None:
        run, self._run = self._run, None
        if run is None:
            return
        await run.client.aclose()
        await asyncio.to_thread(_end, run.process)
        logger.info("Zalo bridge stopped")

    async def step(self, wanted: bool) -> None:
        """One round of the job: notice a dead process, then start or stop the bridge as wanted."""
        run = self._run
        if run is not None and run.process.poll() is not None:
            code = run.process.poll()
            self._run = None
            await run.client.aclose()
            self._failed(f"the bridge exited with code {code}")
        if not wanted or not self.installed():
            await self.stop()
            return
        if self._run is None and self._clock() >= self._retry_at:
            await self._start()

    async def _start(self) -> None:
        self_url = self._self_url()
        if self_url is None:
            self._error = "the service is not listening yet"
            return
        node = self._runner.which("node")
        if node is None:
            self._failed("node is not installed on this machine")
            return
        folder = self._installed_folder()
        port = _free_port()
        secret = secrets.token_hex(32)
        env = {key: value for key, value in os.environ.items() if key.upper() in PASSED_ENV}
        env.update(
            {
                "PEMA_ZALO_PERSONAL_ENABLED": "true",
                "PEMA_ZALO_BRIDGE_SECRET": secret,
                "PEMA_ZALO_BRIDGE_HOST": "127.0.0.1",
                "PEMA_ZALO_BRIDGE_PORT": str(port),
                "PEMA_API_BASE_URL": f"{self_url}/v1/hooks/zalo",
                "ZALO_BRIDGE_LOG_LEVEL": "info",
            }
        )
        process = self._runner.spawn(
            [node, "--import", "tsx", "src/index.ts"], folder, env, self._data_dir() / "bridge.log"
        )
        client = self._client_factory(f"http://127.0.0.1:{port}", secret)
        deadline = time.monotonic() + HEALTH_TIMEOUT_S
        while not await client.health():
            if process.poll() is not None or time.monotonic() > deadline:
                await client.aclose()
                await asyncio.to_thread(_end, process)
                self._failed("the bridge did not come up (see bridge.log)")
                return
            await asyncio.sleep(0.25)
        self._run = _Run(process, client, time.monotonic())
        self._failures = 0
        self._error = None
        self.generation += 1
        logger.info("Zalo bridge running on port %d", port)
        self._on_restart()

    def _failed(self, reason: str) -> None:
        self._error = reason
        self._failures += 1
        pause = RESTART_PAUSES_S[min(self._failures, len(RESTART_PAUSES_S)) - 1]
        self._retry_at = self._clock() + pause
        logger.warning("Zalo bridge: %s; trying again in %.0f s", reason, pause)

    def _install(self) -> None:
        runner = self._runner
        node, pnpm = runner.which("node"), runner.which("pnpm")
        if node is None or pnpm is None:
            raise ValueError("cài Node.js 22.13+ và pnpm trên máy chủ trước")
        code, out = runner.run([node, "--version"], SOURCE, 30.0)
        version = _node_version(out)
        if code != 0 or version is None or version < MIN_NODE:
            raise ValueError(f"cần Node.js 22.13 trở lên (máy chủ có {out.strip() or 'không rõ'})")
        package = json.loads((SOURCE / "package.json").read_text(encoding="utf-8"))
        target = self._root() / str(package.get("version", "0"))
        shutil.rmtree(self._root(), ignore_errors=True)
        target.mkdir(parents=True)
        for name in COPIED:
            source = SOURCE / name
            if source.is_dir():
                shutil.copytree(
                    source, target / name, ignore=shutil.ignore_patterns("*.test.ts", "test-*.ts")
                )
            else:
                shutil.copy2(source, target / name)
        code, out = runner.run([pnpm, "install", "--frozen-lockfile", "--prod"], target, INSTALL_TIMEOUT_S)
        self._log = out.splitlines()[-MAX_LOG_LINES:]
        if code != 0:
            shutil.rmtree(self._root(), ignore_errors=True)
            raise ValueError("pnpm install thất bại (xem log)")
        marker = {
            "version": package.get("version"),
            "node": f"{version[0]}.{version[1]}",
            "folder": target.name,
        }
        (self._root() / "installed.json").write_text(json.dumps(marker), encoding="utf-8")

    def _root(self) -> Path:
        return self._data_dir() / "bridge"

    def _marker(self) -> dict[str, Any] | None:
        marker = self._root() / "installed.json"
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return cast(dict[str, Any], data) if isinstance(data, dict) else None

    def _installed_folder(self) -> Path:
        marker = self._marker() or {}
        return self._root() / str(marker.get("folder", ""))


def _node_version(text: str) -> tuple[int, int] | None:
    found = re.search(r"v?(\d+)\.(\d+)", text)
    return None if found is None else (int(found.group(1)), int(found.group(2)))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _end(process: Process) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


__all__ = ["BridgeStatus", "BridgeSupervisor", "Process", "Runner", "SubprocessRunner"]
