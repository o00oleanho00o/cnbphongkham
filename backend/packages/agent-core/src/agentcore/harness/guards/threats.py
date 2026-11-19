"""Prompt-injection and exfiltration patterns for text that will reach a prompt.

Adapted from Hermes Agent ``tools/threat_patterns.py`` (MIT License, Copyright (c) 2025 Nous Research). Each
pattern has a scope; scopes are cumulative: ``all`` applies everywhere, ``context`` adds role hijack and C2
promptware for text that is not user-authored (tool results), ``strict`` adds aggressive checks for writes
that enter the system prompt later (memory notes, skills), where blocking is the right answer. Patterns
anchor on attack vocabulary, not on bossy English ("you must" is common in honest instructions).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final, Literal

ThreatScope = Literal["all", "context", "strict"]

MAX_SCAN_CHARS: Final = 65_536
_FILLER = r"(?:\w+\s+){0,8}"
_SENSITIVE_VAR = r"\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)S?\b"
_MODIFY = r"(update|modify|edit|write|change|append|add\s+to)\s+[^\n]{0,2048}"

_PATTERNS: Final[tuple[tuple[str, str, ThreatScope], ...]] = (
    # Classic prompt injection
    (rf"ignore\s+{_FILLER}(previous|all|above|prior)\s+{_FILLER}instructions", "prompt_injection", "all"),
    (r"system\s+prompt\s+override", "sys_prompt_override", "all"),
    (
        rf"disregard\s+{_FILLER}(your|all|any)\s+{_FILLER}(instructions|rules|guidelines)",
        "disregard_rules",
        "all",
    ),
    (
        rf"act\s+as\s+(if|though)\s+{_FILLER}you\s+{_FILLER}(have\s+no|don't\s+have)\s+{_FILLER}"
        r"(restrictions|limits|rules)",
        "bypass_restrictions",
        "all",
    ),
    (
        r"<!--[^>]{0,512}(?:ignore|override|system|secret|hidden)[^>]{0,512}-->",
        "html_comment_injection",
        "all",
    ),
    (r"<\s*div\s+style\s*=\s*[\"'][^>]{0,2048}display\s*:\s*none", "hidden_div", "all"),
    (
        r"translate\s+[^\n]{0,512}\s+into\s+\w+(?:[\s-]+\w+){0,2}\s+and\s+(execute|run|eval)\b",
        "translate_execute",
        "all",
    ),
    (rf"do\s+not\s+{_FILLER}tell\s+{_FILLER}the\s+user", "deception_hide", "all"),
    # Role / identity hijack
    (rf"you\s+are\s+{_FILLER}now\s+(?:a|an|the)\s+", "role_hijack", "context"),
    (rf"pretend\s+{_FILLER}(you\s+are|to\s+be)\s+", "role_pretend", "context"),
    (rf"output\s+{_FILLER}(system|initial)\s+prompt", "leak_system_prompt", "context"),
    (
        rf"(respond|answer|reply)\s+without\s+{_FILLER}(restrictions|limitations|filters|safety)",
        "remove_filters",
        "context",
    ),
    (rf"you\s+have\s+been\s+{_FILLER}(updated|upgraded|patched)\s+to", "fake_update", "context"),
    (r"\bname\s+yourself\s+\w+", "identity_override", "context"),
    # C2-style promptware
    (r"register\s+(as\s+)?a?\s*node", "c2_node_registration", "context"),
    (r"(heartbeat|beacon|check[\s\-]?in)\s+(to|with)\s+", "c2_heartbeat", "context"),
    (r"pull\s+(down\s+)?(?:new\s+)?task(?:ing|s)?\b", "c2_task_pull", "context"),
    (r"connect\s+to\s+the\s+network\b", "c2_network_connect", "context"),
    (r"you\s+must\s+(?:\w+\s+){0,3}(register|connect|report|beacon)\b", "forced_action", "context"),
    (r"only\s+use\s+one[\s\-]?liners?\b", "anti_forensic_oneliner", "context"),
    (
        rf"never\s+{_FILLER}(?:create|write)\s+{_FILLER}(?:script|file)\s+{_FILLER}disk",
        "anti_forensic_disk",
        "context",
    ),
    (
        r"unset\s+\w*(?:CLAUDE|CODEX|HERMES|AGENT|OPENAI|ANTHROPIC|DEEPSEEK|LLM)\w*",
        "env_var_unset_agent",
        "context",
    ),
    (r"\b(?:cobalt\s*strike|sliver|havoc|mythic|metasploit|brainworm)\b", "known_c2_framework", "context"),
    (r"\bc2\s+(?:server|channel|infrastructure|beacon)\b", "c2_explicit", "context"),
    (r"\bcommand\s+and\s+control\b", "c2_explicit_long", "context"),
    # Exfiltration
    (rf"curl\s+[^\n]{{0,2048}}{_SENSITIVE_VAR}", "exfil_curl", "all"),
    (rf"wget\s+[^\n]{{0,2048}}{_SENSITIVE_VAR}", "exfil_wget", "all"),
    (r"cat\s+[^\n]{0,2048}(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)", "read_secrets", "all"),
    (r"(send|post|upload|transmit)\s+[^\n]{0,2048}\s+(to|at)\s+https?://", "send_to_url", "strict"),
    (
        rf"(include|output|print|share)\s+{_FILLER}"
        r"(conversation|chat\s+history|previous\s+messages|full\s+context|entire\s+context)",
        "context_exfil",
        "strict",
    ),
    # Persistence
    (r"authorized_keys", "ssh_backdoor", "strict"),
    (
        r"(?:\b(?:echo|cat|cp|mv|dd|tee|install|printf|rsync|scp|ln|append|add|write"
        r"|sed|chmod|chown|truncate|rm|touch|curl|wget|git)\b|\bopen\s*\(|>>?)"
        r"[^\n]{0,512}(?:\$HOME/\.ssh|~/\.ssh)",
        "ssh_access",
        "strict",
    ),
    (
        rf"{_MODIFY}(?:AGENTS\.md|CLAUDE\.md|SOUL\.md|agent\.toml|\.cursorrules|\.clinerules)",
        "agent_config_mod",
        "strict",
    ),
    # Hardcoded secrets; a value that is itself an env-var NAME (SHOUTY_SNAKE) is not a secret.
    (
        r"(?:api[_-]?key|token|secret|password)\s*[=:]\s*[\"']"
        r"(?!(?-i:[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)[\"'])"
        r"[A-Za-z0-9+/=_-]{20,}",
        "hardcoded_secret",
        "strict",
    ),
)

# Zero-width, word joiner, invisible operators, BOM, bidi embeddings, overrides and isolates.
INVISIBLE_CHARS: Final = frozenset(
    "\u200b\u200c\u200d\u2060\u2062\u2063\u2064\ufeff\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)

_INCLUDED_BY: Final[dict[ThreatScope, tuple[ThreatScope, ...]]] = {
    "all": ("all", "context", "strict"),
    "context": ("context", "strict"),
    "strict": ("strict",),
}


def _compile() -> dict[ThreatScope, list[tuple[re.Pattern[str], str]]]:
    compiled: dict[ThreatScope, list[tuple[re.Pattern[str], str]]] = {"all": [], "context": [], "strict": []}
    for pattern, pattern_id, scope in _PATTERNS:
        for target in _INCLUDED_BY[scope]:
            compiled[target].append((re.compile(pattern, re.IGNORECASE), pattern_id))
    return compiled


_COMPILED: Final = _compile()


def scan_for_threats(text: str, scope: ThreatScope) -> list[str]:
    """Pattern ids found in ``text``; invisible characters are reported as ``invisible_unicode_U+XXXX``."""
    if not text:
        return []
    text = text[:MAX_SCAN_CHARS]
    # Invisible characters are checked on the raw text: NFKC can remove them.
    findings = [f"invisible_unicode_U+{ord(ch):04X}" for ch in sorted(set(text) & INVISIBLE_CHARS)]
    # NFKC folds full-width and compatibility forms (ｃａｔ -> cat) so they cannot dodge the patterns.
    normalised = unicodedata.normalize("NFKC", text)
    findings.extend(pattern_id for pattern, pattern_id in _COMPILED[scope] if pattern.search(normalised))
    return findings
