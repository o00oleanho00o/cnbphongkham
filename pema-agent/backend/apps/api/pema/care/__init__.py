"""Per-patient care agent (package M, see docs/PLAN-AI01-M.md). New code, not a port of zalo-agent.

M1: tables (``models``), the 1-to-1 pairing of patient and care agent (``pairing``), the ports of other
packages (``ports``) and the synthetic dev data (``seed``).

M2a: care events (``events``), the 3-level priority queue (``priority``), the send window (``window``), the
turn loop with its event bus and sequential worker (``loop``), the 06:00 tick (``tick``) and the Postgres
store of the loop (``store``). ``testing`` holds the in-memory fakes of the ports for tests.

M2c: staff routing with the SLA and the chain that always ends at the 24/7 on-call contact (``routing``,
``routing_types``, ``routing_store``, ``oncall``), the one template message of an out-of-hours handoff
(``patient_notices``) and the pause and reconcile of scheduled reminders while a person has the conversation
(``reminders``, ``reminder_store``). ``testing_routing`` holds the fakes and a fully wired rig.
"""
