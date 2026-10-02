"""``TaskResult``: the ONLY thing a specialist agent hands back to the care agent (PLAN-AI01-M section 9).

New module (not a port). The care agent reads FIELDS, never the free text of a specialist: it branches on
``needs_human``, ``confidence``, the number of ``citations`` and the structured ``artifacts``. ``summary``
is a
short human-readable line for the staff timeline and the review item; it is capped so a runaway model cannot
smuggle a long document through it.

Rules enforced here, not left to the prompt:

* the model is not trusted with ``needs_human``: ``TaskResult.finalize`` is how the specialist code (and the
  ``KnowledgeAgent`` with no citation) forces it to ``True``;
* ``confidence`` is clamped to ``[0, 1]`` by validation; a missing value is ``0.0`` (a result the model did
  not
  rate is a result nobody should auto-send);
* ``artifacts`` hold structured data only (a slot, a draft id, a checklist outcome), never a patient's name or
  phone number.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import json_schema_of
from pema_contracts.common import JsonObject

SUMMARY_MAX_CHARS = 600


class Citation(BaseModel):
    """One knowledge-base source a statement rests on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=300)


class TaskResult(BaseModel):
    """``TaskResult{summary, artifacts[], citations[], needs_human, confidence}`` of the plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str = Field(default="", max_length=SUMMARY_MAX_CHARS)
    artifacts: list[JsonObject] = Field(default_factory=list[JsonObject])
    citations: list[Citation] = Field(default_factory=list[Citation])
    needs_human: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    def with_needs_human(self, summary: str | None = None) -> TaskResult:
        """The same result with ``needs_human`` forced on (a specialist code path never lowers it)."""
        update: dict[str, Any] = {"needs_human": True}
        if summary is not None:
            update["summary"] = summary[:SUMMARY_MAX_CHARS]
        return self.model_copy(update=update)


def needs_human_result(summary: str, *, artifacts: list[JsonObject] | None = None) -> TaskResult:
    """The result of a delegation that could not finish: a person takes over (confidence 0)."""
    return TaskResult(
        summary=summary[:SUMMARY_MAX_CHARS],
        artifacts=list(artifacts or []),
        needs_human=True,
        confidence=0.0,
    )


def task_result_schema() -> JsonObject:
    """JSON Schema of ``TaskResult`` as the argument schema of the ``submit_result`` tool (root is an object,
    no ``$ref``: the same shape rules the other tools follow, see ``function_tool``)."""
    return json_schema_of(TaskResult)
