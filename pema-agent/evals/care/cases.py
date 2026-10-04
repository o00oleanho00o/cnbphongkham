"""The labelled synthetic cases of the care eval (``cases.yaml``) and the facts derived from them.

New module (not a port). A case is one patient turn: what the patient wrote (``texts``), the label (depth
D1-D5, the expected action and ``required_skill``) and the context the skill ``handoff`` also weighs (VIP,
identity verified, hour of day, hours since a procedure, history flags, how often the question was asked).

The labels are written from PLAN-AI01-M sections 4 and 6 (the temporary default matrix, ``pending doctor
approval``), NOT from running the code, so a disagreement is either a defect or a label the doctor should
rule on. The model's answer for D2-D4 is not part of the file: it comes from the run (an oracle that returns
the label, the rules alone, or a real model). ``conf`` and ``intent`` are what the oracle says besides the
depth.

Everything is synthetic: no name, no phone number, no clinic data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evals.care.yaml_subset import Item, Scalar, parse_cases
from pema.care.handoff_types import Depth, HandoffAction
from pema.policy.text_normalize import to_nfc

CASES_PATH = Path(__file__).with_name("cases.yaml")

_KNOWN_KEYS = frozenset(
    {
        "id",
        "text",
        "texts",
        "depth",
        "action",
        "skill",
        "intent",
        "vip",
        "verified",
        "hour",
        "procedure_hours_ago",
        "complex_history",
        "past_complaint",
        "pending_doctor_work",
        "repeat_count",
        "conf",
        "note",
    }
)


class CaseError(ValueError):
    """A case that is missing a field or has a value out of range."""


@dataclass(frozen=True)
class CareCase:
    id: str
    texts: tuple[str, ...]
    depth: Depth
    action: HandoffAction
    skill: str
    intent: str | None = None
    vip: bool = False
    verified: bool = True
    hour: int = 10
    procedure_hours_ago: int | None = None
    complex_history: bool = False
    past_complaint: bool = False
    pending_doctor_work: bool = False
    repeat_count: int = 0
    conf: float = 0.9
    note: str = ""

    @property
    def has_diacritics(self) -> bool:
        return any(ord(char) > 127 for char in to_nfc(" ".join(self.texts)))

    @property
    def is_red_flag(self) -> bool:
        return self.depth is Depth.D5


def _bool(item: Item, key: str, default: bool) -> bool:
    value = item.get(key, default)
    if not isinstance(value, bool):
        raise CaseError(f"{item.get('id')}: {key} must be true or false")
    return value


def _int(item: Item, key: str, default: int | None) -> int | None:
    value = item.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CaseError(f"{item.get('id')}: {key} must be an integer")
    return value


def _str(item: Item, key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise CaseError(f"{item.get('id')}: {key} must be a string")
    return value


def _texts(item: Item) -> tuple[str, ...]:
    if "texts" in item:
        raw = item["texts"]
        if not isinstance(raw, list):
            raise CaseError(f"{item.get('id')}: texts must be a list")
        return tuple(_text(entry, item) for entry in raw)
    return (_text(item.get("text"), item),)


def _text(entry: Scalar | list[Scalar], item: Item) -> str:
    if not isinstance(entry, str):
        raise CaseError(f"{item.get('id')}: a text must be a string")
    return entry


def default_skill(depth: Depth) -> str:
    """The skill of the default matrix when a case names none: D4 and D5 a doctor, the rest anybody."""
    return "medical" if depth.rank >= Depth.D4.rank else "general"


def case_from_item(item: Item) -> CareCase:
    unknown = set(item) - _KNOWN_KEYS
    case_id = _str(item, "id")
    if case_id is None:
        raise CaseError("a case without an id")
    if unknown:
        raise CaseError(f"{case_id}: unknown keys {sorted(unknown)}")
    depth_code = _str(item, "depth")
    action_code = _str(item, "action")
    if depth_code is None or action_code is None:
        raise CaseError(f"{case_id}: depth and action are required")
    try:
        depth = Depth(depth_code)
        action = HandoffAction(action_code)
    except ValueError as exc:
        raise CaseError(f"{case_id}: {exc}") from exc
    hour = _int(item, "hour", 10)
    conf_raw = item.get("conf", 0.9)
    if isinstance(conf_raw, bool) or not isinstance(conf_raw, int | float) or not 0.0 <= conf_raw <= 1.0:
        raise CaseError(f"{case_id}: conf must be a number in 0..1")
    if hour is None or not 0 <= hour <= 23:
        raise CaseError(f"{case_id}: hour must be 0..23")
    repeat = _int(item, "repeat_count", 0)
    return CareCase(
        id=case_id,
        texts=_texts(item) if ("text" in item or "texts" in item) else (),
        depth=depth,
        action=action,
        skill=_str(item, "skill") or default_skill(depth),
        intent=_str(item, "intent"),
        vip=_bool(item, "vip", default=False),
        verified=_bool(item, "verified", default=True),
        hour=hour,
        procedure_hours_ago=_int(item, "procedure_hours_ago", None),
        complex_history=_bool(item, "complex_history", default=False),
        past_complaint=_bool(item, "past_complaint", default=False),
        pending_doctor_work=_bool(item, "pending_doctor_work", default=False),
        repeat_count=repeat if repeat is not None else 0,
        conf=float(conf_raw),
        note=_str(item, "note") or "",
    )


def load_cases(path: Path = CASES_PATH) -> list[CareCase]:
    cases = [case_from_item(item) for item in parse_cases(path.read_text(encoding="utf-8"))]
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        raise CaseError("duplicate case ids")
    return cases
