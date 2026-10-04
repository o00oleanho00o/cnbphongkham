"""Shared primitives: base model, ISO 8601 +07:00 datetimes, pagination.

Time convention (docs/CONTRACTS-AI01.md): every timestamp that crosses a boundary is ISO 8601 with
an explicit +07:00 offset (``2026-09-20T09:00:00+07:00``). Naive datetimes are rejected on input.
Dates without a time (birth date, due day) use plain ``YYYY-MM-DD``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

VN_TZ = timezone(timedelta(hours=7), "ICT")
"""Fixed +07:00 offset used for every timestamp on the wire (Vietnam has no DST)."""

type JsonObject = dict[str, Any]
"""A JSON object; used for opaque payloads (channel updates, intake answers, audit details)."""


def now_vn() -> datetime:
    """Current time as an aware datetime at +07:00."""
    return datetime.now(UTC).astimezone(VN_TZ)


def to_vn(value: datetime) -> datetime:
    """Convert an aware datetime to +07:00; reject naive input."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must carry an explicit UTC offset (ISO 8601, e.g. +07:00)")
    return value.astimezone(VN_TZ)


def _iso_vn(value: datetime) -> str:
    return to_vn(value).isoformat()


VnDatetime = Annotated[
    datetime,
    AfterValidator(to_vn),
    PlainSerializer(_iso_vn, return_type=str, when_used="json"),
    Field(
        description="ISO 8601 timestamp with an explicit +07:00 offset.",
        examples=["2026-09-20T09:00:00+07:00"],
    ),
]
"""Aware datetime normalised to +07:00, serialised as ISO 8601 with the +07:00 offset."""


class ApiModel(BaseModel):
    """Base class for every DTO: strict about unknown fields, trims strings, ORM friendly."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        from_attributes=True,
        use_enum_values=False,
    )


class Page[T](ApiModel):
    """Offset pagination envelope used by every list endpoint."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class HealthResponse(ApiModel):
    status: str = "ok"
    version: str
