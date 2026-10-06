"""The internal Zalo account as a sender (package O, step O3). New module, no zalo-agent original.

The clinic has customer-facing identities ("Long") and one internal account that rings operators and posts
to the
team group (``agent.accounts.purpose = 'internal'``, package O1). This is the ONLY code that writes through
the
internal account, and it refuses before it sends when:

* there is no enabled internal account (``no_internal_account``: the chain skips the step and logs it);
* the account that would send is not ``internal`` (``account_not_internal``; the check reads the purpose
  from the
  database on every call, so an account switched back to ``customer`` stops being a notifier at once);
* the recipient is the thread of a customer (``customer_recipient``): an operator's linked id, the team
  group and
  the on-call contact are the only targets, and none of them may equal the ``external_ref`` of a conversation;
* the account is not running (``account_not_running``, retryable).

A message goes out as a normal (not ``proactive``) send: the daily cap, window and gap of the customer channel
protect customers from spam and must not swallow a notice for the operators, and the kill switch of the
channel
is not this account's business. Volume is bounded by the outbox itself (one text per notice and step).
"""

from __future__ import annotations

from uuid import UUID

from pema.notify.types import (
    ERR_ACCOUNT_NOT_RUNNING,
    ERR_CUSTOMER_RECIPIENT,
    ERR_EXCEPTION,
    ERR_NO_INTERNAL_ACCOUNT,
    ERR_NOT_INTERNAL,
    ERR_SEND_REJECTED,
    InternalDirectory,
    InternalTarget,
    InternalTargetKind,
    StepResult,
)
from pema.shared.logger import create_logger
from pema_contracts.channel import ChannelRegistry, SendStatus, ThreadKind

log = create_logger("notify.internal")

INTERNAL_PURPOSE = "internal"


class InternalZaloSender:
    def __init__(self, clinic_id: UUID, registry: ChannelRegistry, directory: InternalDirectory) -> None:
        self._clinic_id = clinic_id
        self._registry = registry
        self._directory = directory

    async def send(self, target: InternalTarget, text: str) -> StepResult:
        account_id = await self._directory.internal_account_id()
        if account_id is None:
            return StepResult.skipped(ERR_NO_INTERNAL_ACCOUNT)
        if await self._directory.account_purpose(account_id) != INTERNAL_PURPOSE:
            log.error("the notifier account is not internal; nothing was sent", account_id=account_id)
            return StepResult.failed(ERR_NOT_INTERNAL)
        if await self._directory.is_customer_thread(target.ref):
            log.error("refused to write to a customer thread through the internal account")
            return StepResult.failed(ERR_CUSTOMER_RECIPIENT)
        channel = self._registry.get_running(self._clinic_id, account_id)
        if channel is None:
            return StepResult.failed(ERR_ACCOUNT_NOT_RUNNING, retryable=True)
        kind = ThreadKind.GROUP if target.kind is InternalTargetKind.GROUP else ThreadKind.USER
        try:
            result = await channel.send_text(target.ref, text, thread_kind=kind, proactive=False)
        except Exception as err:
            log.error("internal send failed", err=err, account_id=account_id)
            return StepResult.failed(ERR_EXCEPTION, retryable=True)
        if result.status is SendStatus.REJECTED:
            code = result.error_code.value if result.error_code is not None else ERR_SEND_REJECTED
            return StepResult.failed(code, retryable=False)
        return StepResult.sent()
