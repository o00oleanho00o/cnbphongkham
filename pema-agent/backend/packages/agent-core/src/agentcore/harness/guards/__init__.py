"""Technical guards: injection patterns and secret masking used by the built-in hooks."""

from __future__ import annotations

from agentcore.harness.guards.secrets import REDACTED, SecretRedactor
from agentcore.harness.guards.threats import ThreatScope, scan_for_threats

__all__ = ["REDACTED", "SecretRedactor", "ThreatScope", "scan_for_threats"]
