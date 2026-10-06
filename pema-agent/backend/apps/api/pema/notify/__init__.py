"""Notifications of the shared inbox (package O, step O3): who is told, how, and what happens when nobody
answers. New package, no zalo-agent original.

Layout (state and rules stay in ``pema.clinic.actions``, this package holds the senders and the loops):

* ``consumer``: delivers the rows of ``clinic.notification_outbox`` along the chain in-app now, push when a
  token exists and the provider is on, the personal Zalo bell after ``ack_timeout`` unless acknowledged; the
  team group and the on-call contact are single steps;
* ``providers``: ``InAppProvider``, ``ZaloBellProvider``, ``TeamGroupProvider``, ``OnCallBellProvider``, the
  ``PushProvider`` Protocol with ``FakePushProvider`` and the disabled ``FcmApnsPushProvider`` skeleton;
* ``internal``: the only code that writes through the internal Zalo account, with its guards (the account must
  have ``purpose = internal``, the recipient must not be a customer);
* ``link``: the one-time code that binds an operator's personal Zalo, and the guard that keeps every message
  to the internal account out of the customer inbox;
* ``staff_notify`` and ``sla``: the production adapters of package M's ``StaffNotify`` and ``SlaScheduler``;
* ``store``: the SQL-backed stores (through ``pema.clinic.actions``); ``testing``: in-memory fakes.

Nothing here imports ``pema.clinic.models`` (the agent-side import contract). Logs carry ids and codes only.
"""
