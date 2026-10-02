"""Specialist agents of the care agent (package M, step M4): Scheduler, Knowledge, Reviewer.

New code, not a port. They are DATA (``spec.SpecialistSpec`` -> an ``agent.agents`` record) plus a few tool
builders, not three classes with their own loops: the loop is the shared one (``runner``), the tool set is the
allowlist of the record, the answer is a ``TaskResult``. Delegation is at depth 1 only (``delegate``).

This package ``__init__`` imports nothing on purpose: ``pema.care.ports`` imports ``spec`` and every other
module of the package imports ``ports``.
"""
