"""The service's key-value store: JSON values under string keys, in SQLite at ``<data dir>/zalo.db``.

The same async API the agent's ``PluginStorage`` gave the old plugin (``get``, ``put``, ``delete``, ``list`` by
key prefix, same limits) so the account, contact and friend code did not change. One connection in WAL mode,
every call serialized by a lock and run in a worker thread: this is one process with a few writes a second.
Secrets are never written here in clear: ``accounts.AccountStore`` seals them first.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Final

MAX_KEY_CHARS: Final = 300
MAX_VALUE_BYTES: Final = 256 * 1024
MAX_LIST: Final = 1000
_PAST_ANY_KEY: Final = "\U0010ffff"


def _check_key(key: str) -> None:
    if not key or len(key) > MAX_KEY_CHARS or "\x00" in key:
        raise ValueError(f"a key has 1 to {MAX_KEY_CHARS} characters and no NUL")


def _encoded(key: str, value: Any) -> str:
    _check_key(key)
    if value is None:
        raise ValueError("store a value, not None; delete the key instead")
    data = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if "\\u0000" in data:
        raise ValueError("a stored value may not contain the NUL character")
    if len(data.encode("utf-8")) > MAX_VALUE_BYTES:
        raise ValueError(f"a stored value may have at most {MAX_VALUE_BYTES} bytes as JSON")
    return data


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID"
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    async def get(self, key: str) -> Any | None:
        _check_key(key)
        rows = await self._run("SELECT value FROM kv WHERE key = ?", (key,))
        return json.loads(rows[0][0]) if rows else None

    async def put(self, key: str, value: Any) -> None:
        data = _encoded(key, value)
        await self._run(
            "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, data),
        )

    async def put_many(self, items: list[tuple[str, Any]]) -> None:
        """Writes all of them or none (one transaction)."""
        encoded = [(key, _encoded(key, value)) for key, value in items]

        def work() -> None:
            with self._lock:
                self._db.execute("BEGIN")
                try:
                    self._db.executemany(
                        "INSERT INTO kv (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        encoded,
                    )
                    self._db.execute("COMMIT")
                except BaseException:
                    self._db.execute("ROLLBACK")
                    raise

        await asyncio.to_thread(work)

    async def delete(self, key: str) -> bool:
        _check_key(key)
        return await self._run("DELETE FROM kv WHERE key = ?", (key,), changed=True) == 1

    async def list(self, prefix: str = "", *, limit: int = MAX_LIST) -> list[tuple[str, Any]]:
        """The records whose key starts with ``prefix``, in key order."""
        rows = await self._run(
            "SELECT key, value FROM kv WHERE key >= ? AND key < ? ORDER BY key LIMIT ?",
            (prefix, prefix + _PAST_ANY_KEY, max(1, min(limit, MAX_LIST))),
        )
        return [(key, json.loads(value)) for key, value in rows]

    async def _run(self, sql: str, args: tuple[Any, ...], *, changed: bool = False) -> Any:
        def work() -> Any:
            with self._lock:
                cursor = self._db.execute(sql, args)
                return cursor.rowcount if changed else cursor.fetchall()

        return await asyncio.to_thread(work)
