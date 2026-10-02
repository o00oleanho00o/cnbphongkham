"""Per-patient care agent (package M, see docs/PLAN-AI01-M.md). New code, not a port of zalo-agent.

M1: tables (``models``), the 1-to-1 pairing of patient and care agent (``pairing``), the ports of other
packages (``ports``) and the synthetic dev data (``seed``).

M2a: care events (``events``), the 3-level priority queue (``priority``), the send window (``window``), the
turn loop with its event bus and sequential worker (``loop``), the 06:00 tick (``tick``) and the Postgres
store of the loop (``store``). ``testing`` holds the in-memory fakes of the ports for tests.

M4: the structured answer of a specialist (``task_result``), the per-turn budget of delegations
(``budget``) and the three specialist agents with the ``delegate`` tool (``specialists``).
"""
