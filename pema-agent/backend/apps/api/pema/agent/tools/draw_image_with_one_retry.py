# ported from: src/agent/tools/draw-image-with-one-retry.ts
"""Call the image provider; on a miss, TELL THE USER and retry exactly ONCE.

Why exactly once: the error "ran to the end without producing an image" is non-deterministic behaviour of
the upstream model (see ``image_retry_policy``); measured, calling again almost surely works: 9/9. A
second retry would mostly lengthen the wait: each drawing costs 1-3 minutes, with three attempts people
leave before the image arrives.

Why the user MUST be told before the retry: they already heard the promise "wait 1-3 minutes" at the start
of the turn, yet the measured failing attempt ate 129.9 seconds. Retrying silently makes them sit still
for almost 4 minutes after a 3 minute promise: exactly the kind of silence that the pre-notice of
``create_image_tool`` was written to avoid.

A failing ``bao_thu_lai`` (the notice) must NOT kill the drawing: being able to send the image is worth
more than being able to send the note. Same handling as the pre-notice of the tool.

Split from ``create_image_tool`` so the retry branch can be tested without building a whole
``ToolContext``, and so the tool stays under the 200 line ceiling.

Forced deviation: ``Promise<void> | void`` becomes ``Awaitable[None] | None``; the callbacks may be sync
or async."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from pema.images.image_generation_client import GeneratedImage, GenerateImageParams
from pema.images.image_retry_policy import la_loi_ve_hut_anh


async def ve_voi_mot_lan_thu_lai(
    generate: Callable[[GenerateImageParams], Awaitable[GeneratedImage]],
    params: GenerateImageParams,
    bao_thu_lai: Callable[[], Awaitable[None] | None],
) -> GeneratedImage:
    try:
        return await generate(params)
    except Exception as err:
        # Every other error goes straight out: timeout, wrong key, quota exhausted: calling again only
        # costs more time and changes nothing.
        if not la_loi_ve_hut_anh(err):
            raise

        try:
            outcome = bao_thu_lai()
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:  # noqa: S110 - a failed notice must not kill the drawing (see the docstring)
            pass

        # If the second attempt fails too, let the error fly: the tool outside does the honest telling
        return await generate(params)
