"""What an item must be before it is stored. Everything that reaches the prompt is checked, whoever wrote
it: an administrator pastes from elsewhere too. Problems stop the save; warnings are shown and the save
goes on."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from agentcore.harness.guards.threats import scan_for_threats

from .models import KINDS, STATUSES, Item
from .scope import clean

NAME: Final = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
MAX_DESCRIPTION: Final = 300
MAX_BODY: Final = 20_000
MAX_RULES_BODY: Final = 6_000
"""Rules and persona go into every question in full, so they are shorter than a skill."""
MAX_SCOPES: Final = 20
PHONE: Final = re.compile(r"(?<!\d)(?:\+?84|0)[\s.-]?[3-9](?:[\s.-]?\d){8}(?!\d)")
CCCD: Final = re.compile(r"(?<!\d)\d{12}(?!\d)")


class ItemError(ValueError):
    """The item cannot be stored; the message says what to change."""


@dataclass(frozen=True, slots=True)
class Checked:
    scopes: list[str]
    warnings: list[str]


def check(item: Item) -> Checked:
    """Raises ``ItemError`` for a problem; returns the cleaned scopes and the warnings."""
    if item.kind not in KINDS:
        raise ItemError(f"kind must be one of {', '.join(KINDS)}")
    if item.status not in STATUSES:
        raise ItemError(f"status must be one of {', '.join(STATUSES)}")
    if not NAME.fullmatch(item.name):
        raise ItemError("name: 1-64 of a-z, 0-9, '.', '_', '-', starting with a letter or digit")
    description = item.description.strip()
    if not description or "\n" in description:
        raise ItemError("description must be one non-empty line")
    if len(description) > MAX_DESCRIPTION:
        raise ItemError(f"description is longer than {MAX_DESCRIPTION} characters")
    limit = MAX_BODY if item.kind == "skill" else MAX_RULES_BODY
    if not item.body.strip():
        raise ItemError("the text is empty")
    if len(item.body) > limit:
        raise ItemError(f"the text has {len(item.body)} characters; a {item.kind} may have {limit}")
    if len(item.scopes) > MAX_SCOPES:
        raise ItemError(f"at most {MAX_SCOPES} scopes")
    try:
        scopes = clean(item.scopes)
    except ValueError as err:
        raise ItemError(str(err)) from err
    findings = scan_for_threats(f"{item.description}\n{item.body}", "strict")
    if findings:
        raise ItemError(
            f"the text looks like an instruction injection ({', '.join(findings)}): write what to do plainly"
        )
    return Checked(scopes, _warnings(item))


def _warnings(item: Item) -> list[str]:
    text = f"{item.description}\n{item.body}"
    found: list[str] = []
    if PHONE.search(text):
        found.append("the text holds something that looks like a phone number")
    if CCCD.search(text):
        found.append("the text holds a 12-digit number that may be an ID card number")
    return found
