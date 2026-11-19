"""One rich-text span as the Zalo channels send it (zca-js ``Style``: ``start``, ``len``, ``st``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TextStyle(BaseModel):
    """Offsets are UTF-16 units of the text the span belongs to."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    start: int = Field(ge=0)
    length: int = Field(ge=1)
    style: str = Field(description="zca-js style code, e.g. 'b', 'i', 'u', 'c_db342e', 'f_18'.")
