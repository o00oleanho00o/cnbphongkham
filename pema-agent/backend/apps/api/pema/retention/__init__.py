"""Data retention: delete expired data of the installation's clinic (package H2; new, no TS source).

``policy`` (days per group from ``PEMA_RETENTION_*``, 0 = keep), ``rules`` (the SQL, as data), ``runner``
(batches, advisory lock, dry run, audit row) and ``schedule`` (the periodic loop that the worker and the API
process start). The command line is ``python -m pema.workers.retention``. Never imports ``pema.api``,
``pema.workers`` or ``pema.bootstrap``: the two processes and the CLI import this package, not the other way
round.
"""
