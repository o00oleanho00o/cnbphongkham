"""Error codes and the error envelope shared by the API, the workers, the channels and the FE."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from pema_contracts.common import ApiModel, JsonObject


class ErrorCode(StrEnum):
    """Stable machine-readable error codes. ``message`` is Vietnamese UI text; ``code`` never changes."""

    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    VALIDATION_FAILED = "validation_failed"
    VERSION_CONFLICT = "version_conflict"
    """Optimistic locking: the ``version`` sent is not the stored one."""
    DUPLICATE_REQUEST = "duplicate_request"
    """Same ``Idempotency-Key`` with a different body."""
    INVALID_STATE = "invalid_state"
    """E.g. task already resolved, review item already decided."""
    APPOINTMENT_CONFLICT = "appointment_conflict"
    RATE_LIMITED = "rate_limited"
    NOT_IMPLEMENTED = "not_implemented"
    CONSENT_REQUIRED = "consent_required"
    MARKETING_OPT_OUT = "marketing_opt_out"
    CHANNEL_UNAVAILABLE = "channel_unavailable"
    CHANNEL_KILL_SWITCH_ON = "channel_kill_switch_on"
    CHANNEL_DAILY_CAP_REACHED = "channel_daily_cap_reached"
    CHANNEL_OUTSIDE_SEND_WINDOW = "channel_outside_send_window"
    CHANNEL_RECIPIENT_NOT_REACHABLE = "channel_recipient_not_reachable"
    """E.g. personal Zalo: recipient is not a friend / never messaged the bot."""
    CHANNEL_WEBHOOK_REJECTED = "channel_webhook_rejected"
    REVIEW_REQUIRED = "review_required"
    """Content with medical meaning cannot be sent without a human decision."""
    AI_UNAVAILABLE = "ai_unavailable"
    POLICY_DENIED = "policy_denied"
    """The active policy profile (staff_assistant / patient_channel) forbids the operation."""
    IDENTITY_NOT_VERIFIED = "identity_not_verified"
    """patient_channel: zalo_uid is not yet linked to a verified patient record."""
    TOOL_UNAVAILABLE = "tool_unavailable"
    """Tool is disabled by agent, account, channel or policy profile."""
    INVALID_SCHEDULE = "invalid_schedule"
    """Schedule rejected by the parser (too dense, past, bad cron)."""
    MCP_SERVER_UNAPPROVED = "mcp_server_unapproved"
    """MCP server not bound to the agent (default-deny) or tool fingerprint drifted (needs re-approval)."""
    KB_SOURCE_INVALID = "kb_source_invalid"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    THREAD_LOCKED = "thread_locked"
    """Another operator holds the thread (package O, step O2): only the holder replies; the others take over
    first. ``details`` carries the holder id and the ``assignment_version`` to take over from."""
    NO_IDENTITY = "no_identity"
    """Package O, step O4: the conversation has no clinic identity to send through (no ``account_id`` and the
    channel has no single customer account). The message stays ``queued`` with this code on it."""
    INTERNAL = "internal"


ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.VALIDATION_FAILED: 422,
    ErrorCode.VERSION_CONFLICT: 409,
    ErrorCode.DUPLICATE_REQUEST: 409,
    ErrorCode.INVALID_STATE: 409,
    ErrorCode.APPOINTMENT_CONFLICT: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.CONSENT_REQUIRED: 422,
    ErrorCode.MARKETING_OPT_OUT: 422,
    ErrorCode.CHANNEL_UNAVAILABLE: 503,
    ErrorCode.CHANNEL_KILL_SWITCH_ON: 409,
    ErrorCode.CHANNEL_DAILY_CAP_REACHED: 429,
    ErrorCode.CHANNEL_OUTSIDE_SEND_WINDOW: 409,
    ErrorCode.CHANNEL_RECIPIENT_NOT_REACHABLE: 422,
    ErrorCode.CHANNEL_WEBHOOK_REJECTED: 401,
    ErrorCode.REVIEW_REQUIRED: 409,
    ErrorCode.AI_UNAVAILABLE: 503,
    ErrorCode.POLICY_DENIED: 403,
    ErrorCode.IDENTITY_NOT_VERIFIED: 409,
    ErrorCode.TOOL_UNAVAILABLE: 422,
    ErrorCode.INVALID_SCHEDULE: 422,
    ErrorCode.MCP_SERVER_UNAPPROVED: 409,
    ErrorCode.KB_SOURCE_INVALID: 422,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.THREAD_LOCKED: 409,
    ErrorCode.NO_IDENTITY: 409,
    ErrorCode.INTERNAL: 500,
}
"""HTTP status each code maps to. The mapping is part of the contract."""


class ErrorBody(ApiModel):
    code: ErrorCode
    message: str = Field(description="Vietnamese text safe to show in the UI. Never contains PII.")
    details: JsonObject | None = None
    request_id: str | None = None


class ErrorResponse(ApiModel):
    """Body of every non-2xx response."""

    error: ErrorBody


class DomainError(Exception):
    """Raised by ``actions/`` and mapped to ``ErrorResponse`` by the API layer.

    Also used by channels, the agent engine and the scheduler so that one vocabulary crosses all
    boundaries. ``message`` must not contain PII or clinical content.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: JsonObject | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.details = details

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_STATUS[self.code]

    def to_response(self, request_id: str | None = None) -> ErrorResponse:
        return ErrorResponse(
            error=ErrorBody(
                code=self.code,
                message=self.message,
                details=self.details,
                request_id=request_id,
            )
        )
