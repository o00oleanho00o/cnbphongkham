"""Live updates and presence (package ST-R): events from the worker and the API reach the browsers.

``bus`` (port + in-memory adapter + wire encoding), ``redis_bus`` (adapter), ``publisher`` (``emit_live``, the
one call the business code makes after a commit), ``hub`` (fan-out to the open streams, limits), ``sse`` (the
stream body), ``presence`` (who has a conversation open), ``services`` (the objects of a process).
Nothing here imports ``pema.clinic``, ``pema.api`` or ``pema.workers``; the business code calls ``emit_live``.
"""

from pema.live.publisher import emit_live

__all__ = ["emit_live"]
