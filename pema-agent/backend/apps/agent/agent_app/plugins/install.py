"""Puts plugins into the installed-plugins folder: from a folder on this server, a zip upload or a git
repository, with their Python requirements.

Everything is unpacked into a staging folder next to the target first and checked there: a manifest the
service understands, no links, no path leaving the folder, bounded sizes. Requirements are installed with pip
(or uv) into the plugin's own ``.deps`` folder. Only then does the staging folder replace the plugin's folder.
Installing runs the plugin's code later, and pip may run a package's build scripts now: only an admin may
install, and plugins are trusted code.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import uuid4

from agent_app.plugins.host import DEPS_DIR
from agent_app.plugins.manifest import (
    PLUGIN_API,
    TOML_MANIFEST,
    YAML_MANIFESTS,
    PluginError,
    PluginManifest,
    read_manifest,
)

MAX_ZIP_BYTES: Final = 20 * 1024 * 1024
MAX_UNPACKED_BYTES: Final = 64 * 1024 * 1024
MAX_FILES: Final = 2000
GIT_TIMEOUT_S: Final = 120.0
PIP_TIMEOUT_S: Final = 600.0
OUTPUT_TAIL_CHARS: Final = 2000
GIT_REF: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
REQUIREMENT: Final = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,-]+\])?"
    r"(\s*(==|!=|<=|>=|~=|<|>)\s*[A-Za-z0-9.*+!_-]+(\s*,\s*(==|!=|<=|>=|~=|<|>)\s*[A-Za-z0-9.*+!_-]+)*)?$"
)
SKIPPED: Final = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", DEPS_DIR)

Runner = Callable[[Sequence[str], float], str]
"""Runs a command (no shell) within a timeout and returns its output; raises ``InstallError`` on failure."""


class InstallError(PluginError):
    def __init__(self, message: str) -> None:
        super().__init__("install", message)


@dataclass(frozen=True, slots=True)
class Staged:
    folder: Path
    manifest: PluginManifest
    install: dict[str, Any]
    """Where it came from, stored with the plugin's state."""


def run_command(command: Sequence[str], timeout_s: float) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "PIP_NO_INPUT": "1"}
    try:
        done = subprocess.run(  # noqa: S603 - a fixed program and checked arguments, no shell
            list(command), capture_output=True, text=True, timeout=timeout_s, env=env, check=False
        )
    except subprocess.TimeoutExpired as err:
        raise InstallError(f"{command[0]} took longer than {timeout_s:.0f}s") from err
    except OSError as err:
        raise InstallError(f"cannot run {command[0]}: {err}") from err
    if done.returncode != 0:
        output = (done.stderr or done.stdout or "").strip()[-OUTPUT_TAIL_CHARS:]
        raise InstallError(f"{Path(command[0]).name} failed (exit {done.returncode}): {output}")
    return done.stdout


class PluginInstaller:
    def __init__(self, root: Path, *, runner: Runner = run_command, allow_local_git: bool = False) -> None:
        self.root = root
        self._run = runner
        self._allow_local_git = allow_local_git

    # --- staging ---

    def stage_folder(self, path: Path) -> Staged:
        source = path.resolve()
        if not source.is_dir():
            raise InstallError(f"{path} is not a folder")
        staging = self._staging()
        try:
            shutil.copytree(source, staging / "plugin", symlinks=True, ignore=SKIPPED)
            return self._check(staging, {"kind": "folder", "ref": str(source)})
        except BaseException:
            remove_tree(staging)
            raise

    def stage_zip(self, data: bytes) -> Staged:
        if len(data) > MAX_ZIP_BYTES:
            raise InstallError(f"the zip may have at most {MAX_ZIP_BYTES} bytes")
        staging = self._staging()
        try:
            _unzip(data, staging / "plugin")
            digest = hashlib.sha256(data).hexdigest()
            return self._check(staging, {"kind": "zip", "ref": f"sha256:{digest}"})
        except BaseException:
            remove_tree(staging)
            raise

    def stage_git(self, url: str, ref: str | None = None) -> Staged:
        self._check_git_url(url)
        if ref is not None and (not GIT_REF.match(ref) or ".." in ref):
            raise InstallError("the git ref may use letters, digits and . _ / - only")
        staging = self._staging()
        try:
            target = staging / "plugin"
            command = ["git"]
            if not self._allow_local_git:
                command += ["-c", "protocol.file.allow=never"]
            command += ["clone", "--depth", "1", "--single-branch", "--no-tags"]
            if ref is not None:
                command += ["--branch", ref]
            self._run([*command, "--", url, str(target)], GIT_TIMEOUT_S)
            commit = self._run(["git", "-C", str(target), "rev-parse", "HEAD"], GIT_TIMEOUT_S).strip()
            remove_tree(target / ".git")
            return self._check(staging, {"kind": "git", "ref": url, "git_ref": ref, "commit": commit})
        except BaseException:
            remove_tree(staging)
            raise

    # --- requirements and the swap ---

    def install_requirements(self, staged: Staged) -> None:
        requires = staged.manifest.requires
        if not requires:
            return
        bad = [r for r in requires if not REQUIREMENT.match(r.strip())]
        if bad:
            raise InstallError(f"requirements must be plain package specs (name, extras, versions): {bad}")
        target = str(staged.folder / DEPS_DIR)
        self._run([*_pip(), "--target", target, *[r.strip() for r in requires]], PIP_TIMEOUT_S)

    def commit(self, staged: Staged) -> Path:
        """Moves the staged plugin into ``root/<name>``, replacing an older copy."""
        target = self.root / staged.manifest.name
        old: Path | None = None
        if target.exists():
            old = self.root / f".old-{staged.manifest.name}-{uuid4().hex[:8]}"
            target.rename(old)
        try:
            staged.folder.rename(target)
        except OSError:
            if old is not None:
                old.rename(target)
            raise
        finally:
            remove_tree(staged.folder.parent)
        if old is not None:
            remove_tree(old)
        return target

    def discard(self, staged: Staged) -> None:
        remove_tree(staged.folder.parent)

    def uninstall(self, name: str) -> None:
        remove_tree(self.root / name)

    def _staging(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f".staging-{uuid4().hex}"
        staging.mkdir()
        return staging

    def _check(self, staging: Path, install: dict[str, Any]) -> Staged:
        folder = _plugin_folder(staging / "plugin")
        _refuse_links(folder)
        try:
            manifest = read_manifest(folder)
        except ValueError as err:
            raise InstallError(f"the manifest cannot be read: {err}") from err
        if manifest is None:
            raise InstallError("no plugin.toml or plugin.yaml at the top of the plugin")
        if manifest.api != PLUGIN_API:
            raise InstallError(f"plugin API {manifest.api}; this service speaks {PLUGIN_API}")
        if not (folder / manifest.entry).is_file():
            raise InstallError(f"the entry file {manifest.entry} is missing")
        if folder != staging / "plugin":
            moved = staging / "plugin-root"
            folder.rename(moved)
            remove_tree(staging / "plugin")
            folder = moved.rename(staging / "plugin")
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        return Staged(folder, manifest, {**install, "version": manifest.version, "installed_at": stamp})

    def _check_git_url(self, url: str) -> None:
        parts = urlsplit(url)
        if url.startswith("-") or len(url) > 500:
            raise InstallError("not a git URL")
        if parts.scheme == "https" and parts.hostname:
            if parts.username or parts.password:
                raise InstallError("credentials in the URL are not accepted; use a public repository")
            return
        if self._allow_local_git and (parts.scheme == "file" or Path(url).is_dir()):
            return
        raise InstallError("use an https:// git URL")


def remove_tree(path: Path) -> None:
    """Removes a folder, read-only files too (git's pack files on Windows)."""

    def retry_writable(function: Callable[..., Any], target: str, _: BaseException) -> None:
        os.chmod(target, stat.S_IWRITE)
        function(target)

    if path.exists():
        shutil.rmtree(path, onexc=retry_writable)


def _pip() -> list[str]:
    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
    uv = shutil.which("uv")
    if uv is not None:
        return [uv, "pip", "install", "--python", sys.executable]
    raise InstallError("installing requirements needs pip or uv")


def _unzip(data: bytes, target: Path) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as err:
        raise InstallError("not a zip file") from err
    with archive:
        members = archive.infolist()
        if len(members) > MAX_FILES:
            raise InstallError(f"the zip may hold at most {MAX_FILES} entries")
        target.mkdir()
        budget = MAX_UNPACKED_BYTES
        for member in members:
            path = _member_path(member, target)
            if member.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, path.open("wb") as sink:
                while chunk := source.read(64 * 1024):
                    budget -= len(chunk)
                    if budget < 0:
                        raise InstallError(f"the zip unpacks to more than {MAX_UNPACKED_BYTES} bytes")
                    sink.write(chunk)


def _member_path(member: zipfile.ZipInfo, target: Path) -> Path:
    name = member.filename.replace("\\", "/")
    parts = PurePosixPath(name).parts
    if name.startswith("/") or ":" in name or ".." in parts or not parts:
        raise InstallError(f"the zip entry {member.filename!r} leaves the plugin folder")
    if stat.S_ISLNK(member.external_attr >> 16):
        raise InstallError(f"the zip entry {member.filename!r} is a link")
    path = target.joinpath(*parts)
    if not path.resolve().is_relative_to(target.resolve()):
        raise InstallError(f"the zip entry {member.filename!r} leaves the plugin folder")
    return path


def _plugin_folder(unpacked: Path) -> Path:
    """The folder holding the manifest: the top, or the only folder inside it (as GitHub zips are made)."""
    if _has_manifest(unpacked):
        return unpacked
    entries = [p for p in unpacked.iterdir() if not p.name.startswith(".") and p.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir() and _has_manifest(entries[0]):
        return entries[0]
    raise InstallError("no plugin.toml or plugin.yaml at the top of the plugin")


def _has_manifest(folder: Path) -> bool:
    return any((folder / name).is_file() for name in (TOML_MANIFEST, *YAML_MANIFESTS))


def _refuse_links(folder: Path) -> None:
    for path in folder.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise InstallError(f"{path.relative_to(folder)} is a link; plugins may not hold links")
