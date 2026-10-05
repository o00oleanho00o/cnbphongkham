"""The 10 CRM rules as a policy engine that creates scheduler jobs through SchedulerPort. Owner: B2.
Source: prototype/shared/crm-automation.js and crm-data.js.

Layers (each file says what it ports and where it deviates):

* ``dates``, ``rules``, ``records``, ``profile``, ``engine``: PURE. No I/O, no clock; ``now`` is a parameter.
  ``engine.run_rules`` is ``run()`` of crm-automation.js without side effects.
* ``jobs``: PURE policy that turns tasks into ``CreateScheduledJobInput`` (message from an approved
  template, or an agent DRAFT; never a birthday; ``marketing_opt_out`` respected; cap and staleness gates).
* ``store`` (port, in-memory) and ``sql_store`` (Postgres as ``be_app``), ``runner`` (orchestration),
  ``admin`` (list/tune rules for ``/admin/rules``).
"""
