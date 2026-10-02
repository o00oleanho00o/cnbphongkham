"""What the care routes need from the live objects: the service dependency (package M, step M5).

New module (not a port). ``app.state.care`` is filled by the composition root with an implementation of
``pema.care.supervision.CareSupervision``; a bare app has none and the routes answer 503.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from pema.care.supervision import CareSupervision
from pema_contracts.errors import DomainError, ErrorCode

UNAVAILABLE_MESSAGE = "Chức năng theo dõi agent chăm sóc tạm thời chưa dùng được."


def get_care(request: Request) -> CareSupervision:
    care: object = getattr(request.app.state, "care", None)
    if care is None:
        raise DomainError(ErrorCode.CHANNEL_UNAVAILABLE, UNAVAILABLE_MESSAGE)
    return cast("CareSupervision", care)  # the composition root installs a CareSupervision


CareDep = Annotated[CareSupervision, Depends(get_care)]
