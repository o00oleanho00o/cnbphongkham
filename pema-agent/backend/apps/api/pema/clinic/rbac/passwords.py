# ported from: src/server/dashboard-password-store.ts (the hashing part)
"""Password hashing for ``clinic.user_account.password_hash`` (argon2id).

Forced deviation: the original stored ONE dashboard password with ``scrypt`` ("salt:hash") in
``runtime_settings``. The clinic has per-user accounts, so each ``user_account`` row carries an argon2id
hash (``argon2-cffi``, self-describing, own salt per hash). The invariants of the original are kept:

* the password is NEVER stored in clear: reading the database does not reveal it;
* every hash gets its own salt: two accounts with the same password do not look alike;
* a corrupt stored value is "no match" and NEVER falls back to something weaker;
* comparison is constant time (argon2 verifies in constant time with respect to the hash).

``fingerprint`` is the ``passwordFingerprint`` of ``dashboard-auth.ts``: a value stored in each session so a
password change kills every older session.
"""

from __future__ import annotations

import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 8
"""Same floor as the original (``DASHBOARD_PASSWORD`` schema: at least 8 characters)."""

_default_hasher = PasswordHasher()


def hash_password(plain: str, *, time_cost: int | None = None, memory_cost: int | None = None) -> str:
    """argon2id hash with a fresh salt. ``time_cost``/``memory_cost`` exist so tests can use cheap
    parameters; production code never passes them (library defaults, RFC 9106 low-memory profile)."""
    if time_cost is None and memory_cost is None:
        return _default_hasher.hash(plain)
    hasher = PasswordHasher(time_cost=time_cost or 2, memory_cost=memory_cost or 65536)
    return hasher.hash(plain)


def verify_password(stored_hash: str | None, plain: str) -> bool:
    """``True`` only for a correct password. Missing, corrupt or foreign-format hashes are a plain
    ``False``: they must not raise (the caller answers 401 either way) and must not fall back."""
    if not stored_hash:
        return False
    try:
        return _default_hasher.verify(stored_hash, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """The library parameters moved on since this hash was made."""
    try:
        return _default_hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return False


def burn_verification_time(plain: str) -> None:
    """Run one verification against a throw-away hash so that an unknown email costs the same time as a
    wrong password (no user enumeration through timing)."""
    verify_password(_DUMMY_HASH, plain)


def fingerprint(stored_hash: str | None) -> str:
    """Fingerprint of the password in force: sha256 of the stored hash (already hash + salt, so no
    clear text leaves here)."""
    return hashlib.sha256((stored_hash or "").encode("utf-8")).hexdigest()


_DUMMY_HASH = _default_hasher.hash("dummy-password-for-timing-only")
