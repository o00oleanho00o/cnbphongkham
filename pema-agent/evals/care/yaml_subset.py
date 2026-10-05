"""Reader for the small YAML subset of ``cases.yaml``.

New module (not a port). PyYAML is not in the lock file of this repository and the lock file belongs to
another
package, so the case file is written in a strict subset of YAML (which any YAML parser reads identically) and
read here:

* a document that is a sequence of mappings: ``- key: value`` opens an item, ``  key: value`` continues it;
* a scalar is a double-quoted string (JSON escapes), ``true``/``false``/``null``, an integer, a float, or a
  bare word without spaces (``D1``, ``answer``);
* a flow list of such scalars: ``["a", "b"]`` (on ONE line; ``[]`` is the empty list);
* ``#`` starts a comment on a line of its own (a ``#`` inside a quoted string is text).

Anything else raises ``YamlSubsetError`` with the line number: a case file that needs more should switch to
PyYAML (open item) rather than grow this reader.
"""

from __future__ import annotations

import json
import re

type Scalar = str | int | float | bool | None
type Value = Scalar | list[Scalar]
type Item = dict[str, Value]

_KEY = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*):(?:\s+(?P<value>.*))?$")
_BARE = re.compile(r"^[^\s\"'\[\]{},#:]+$")
_INT = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?\d+\.\d+$")


class YamlSubsetError(ValueError):
    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"line {line}: {message}")


def _scalar(token: str, line: int) -> Scalar:
    token = token.strip()
    if token.startswith('"'):
        try:
            parsed: object = json.loads(token)
        except ValueError as exc:
            raise YamlSubsetError(line, f"bad quoted string: {token}") from exc
        if not isinstance(parsed, str):
            raise YamlSubsetError(line, f"bad quoted string: {token}")
        return parsed
    if token in {"true", "false"}:
        return token == "true"  # noqa: S105  - a YAML boolean, not a secret
    if token in {"null", "~"}:
        return None
    if _INT.match(token):
        return int(token)
    if _FLOAT.match(token):
        return float(token)
    if _BARE.match(token):
        return token
    raise YamlSubsetError(line, f"unsupported value: {token}")


def _split_flow(body: str, line: int) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    for char in body:
        if in_string:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            current.append(char)
        elif char == ",":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if in_string:
        raise YamlSubsetError(line, "unterminated string in a list")
    tail = "".join(current)
    if tail.strip() or parts:
        parts.append(tail)
    return parts


def _value(raw: str, line: int) -> Value:
    raw = raw.strip()
    if raw.startswith("["):
        if not raw.endswith("]"):
            raise YamlSubsetError(line, "a list must close on the same line")
        return [_scalar(part, line) for part in _split_flow(raw[1:-1], line)]
    return _scalar(raw, line)


def parse_cases(text: str) -> list[Item]:
    """The items of a case file."""
    items: list[Item] = []
    current: Item | None = None
    for number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            current = {}
            items.append(current)
            body = stripped[2:].strip()
        elif raw_line.startswith((" ", "\t")) and current is not None:
            body = stripped
        else:
            raise YamlSubsetError(number, "expected '- key: value' or an indented 'key: value'")
        match = _KEY.match(body)
        if match is None:
            raise YamlSubsetError(number, f"expected 'key: value', got: {body}")
        key = match.group("key")
        if key in current:
            raise YamlSubsetError(number, f"duplicate key: {key}")
        value = match.group("value")
        if value is None or not value.strip():
            raise YamlSubsetError(number, f"key without a value: {key}")
        current[key] = _value(value, number)
    return items
