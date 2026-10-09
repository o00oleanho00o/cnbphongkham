"""The service's home folder: what it keeps on this machine, so that nothing but the database address comes
from the environment. ``agent serve --home /data`` in a container (a volume), ``~/.pema-agent`` by default.

* ``secret.key``: the key secrets are sealed with (the model API key, plugin secrets and logins), created on
  the first start, readable by its owner only. Losing it makes every stored secret unreadable: back it up.
* ``plugins/<name>/``: each plugin's own files (``ctx.data_dir``).
* ``installed/``: plugins installed from the dashboard or ``agent plugins install``.
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_app.model_settings import SECRET_KEY_ENV
from agent_app.plugins.host import DATA_DIR_ENV
from agent_app.runtime import PLUGIN_DIR_ENV

DEFAULT_HOME: Final = Path.home() / ".pema-agent"
SECRET_KEY_FILE: Final = "secret.key"  # noqa: S105 - a file name, not a key
INSTALLED_DIR: Final = "installed"
_HEX_KEY: Final = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class ServiceHome:
    root: Path

    def secret_key(self) -> str:
        """The key in ``secret.key``, created when the file does not exist yet. A file that holds something
        else is an error, never overwritten: the secrets sealed with it would be lost."""
        path = self.root / SECRET_KEY_FILE
        if not path.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            draft = path.with_name(f"{SECRET_KEY_FILE}.{secrets.token_hex(4)}.tmp")
            fd = os.open(draft, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as file:
                file.write(secrets.token_hex(32) + "\n")
            try:
                os.link(draft, path)  # appears complete or not at all; never replaces an existing key
            except FileExistsError:
                pass
            finally:
                draft.unlink()
        key = path.read_text(encoding="ascii").strip()
        if not _HEX_KEY.fullmatch(key):
            raise ValueError(
                f"{path} does not hold a secret key (64 hex characters); restore it from a backup"
            )
        return key

    def settings(self) -> dict[str, str]:
        """The service settings ``build_runtime`` takes: the secret key and the folders."""
        return {
            SECRET_KEY_ENV: self.secret_key(),
            DATA_DIR_ENV: str(self.root),
            PLUGIN_DIR_ENV: str(self.root / INSTALLED_DIR),
        }
