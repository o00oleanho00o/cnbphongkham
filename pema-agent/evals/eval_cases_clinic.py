"""Dermatology CSKH eval cases for the policy profiles (package P). New file, no zalo-agent original.

The cases live in ``clinic_cases.json`` (data, so the clinic's doctor can read and edit them without Python)
and this module only loads and validates them. It imports nothing from ``pema``: package D1's runner
(``run_eval.py``, the port of ``run-eval.ts``) can load the same file for a REAL model run, and the
deterministic runner is ``backend/apps/api/tests/policy/test_clinic_eval_cases.py`` (fake model, in CI).

Same rule as the original ``eval-case-type.ts``: a case states WHY it exists (``reason``, mandatory), and
expectations are STRUCTURAL (was the model called, which review items exist, what is absent from the
model's input). No case asserts on the semantic content of a model reply: a red eval that flickers is an
eval nobody reads. Everything in the file is fictional and the doctor reviews the wording before it is
trusted.

Case shape::

    id, group, reason, profile ("staff_assistant" | "patient_channel"), kind, input, expect

``kind`` and its ``input`` / ``expect`` keys:

* ``turn``     input: ``messages`` [{text, kind?, sender_name?}], ``identity_verified?``, ``model_reply?``,
               ``setup?`` {phone_on_file?, reception_code?}
               expect: ``handed_off``, ``hand_off_reason?``, ``red_flags?`` (exact list), ``model_called``,
               ``review_kinds?`` (as a set), ``review_count?``, ``outbound?`` (send|hold_for_review|drop),
               ``model_input_must_contain?`` / ``model_input_must_not_contain?``, ``reply_must_contain?`` /
               ``reply_must_not_contain?``, ``identity_after?`` (none|pending|verified)
* ``tools``    input: ``keys``; expect: ``removed``, ``kept``
* ``memory``   input: ``source``; expect: ``allowed``
* ``job``      input: ``job_kind``, ``payload``, ``name?``, ``patient`` {marketing_opt_out}, ``templates``
               {key: is_marketing}; expect: ``action``, ``reason?``
* ``identity`` input: ``link_status``; expect: ``verified``, ``needs_staff_confirmation``
* ``cap``      input: ``patient_known``; expect: ``scope_prefix``, ``same_across_threads``
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CASES_PATH = Path(__file__).with_name("clinic_cases.json")

KINDS = frozenset({"turn", "tools", "memory", "job", "identity", "cap"})
PROFILES = frozenset({"staff_assistant", "patient_channel"})
GROUPS = frozenset(
    {"red_flag", "media", "pii", "outbound", "identity", "tools", "memory", "jobs", "cap", "staff_parity"}
)


@dataclass(frozen=True)
class ClinicEvalCase:
    id: str
    group: str
    reason: str
    profile: str
    kind: str
    input: dict[str, Any]
    expect: dict[str, Any]


def _validate(raw: dict[str, Any]) -> ClinicEvalCase:
    missing = [k for k in ("id", "group", "reason", "profile", "kind", "input", "expect") if k not in raw]
    if missing:
        raise ValueError(f"case {raw.get('id', '?')}: missing {missing}")
    case = ClinicEvalCase(
        **{k: raw[k] for k in ("id", "group", "reason", "profile", "kind", "input", "expect")}
    )
    if not case.reason.strip():
        raise ValueError(f"case {case.id}: a case must say why it exists")
    if case.kind not in KINDS or case.profile not in PROFILES or case.group not in GROUPS:
        raise ValueError(f"case {case.id}: unknown kind, profile or group")
    return case


def load_clinic_cases(path: Path = CASES_PATH) -> list[ClinicEvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = [_validate(raw) for raw in data["cases"]]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids")
    return cases
