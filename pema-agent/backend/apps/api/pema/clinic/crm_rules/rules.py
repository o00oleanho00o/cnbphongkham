# ported from: prototype/shared/crm-data.js (rules)
"""The ten CRM automation rules and the configuration the engine reads.

``DEFAULT_RULES`` is the ``rules`` table of crm-data.js, row for row (id, name, trigger, delayDays,
suggestedAction, priority), with the same ``conditions``: ``protocol`` for d1/d3/d7 and ``marketing`` for
dormant90, dormant180 and birthday. ``actionType: 'staff_task'`` of the original becomes
``send_mode = staff_task``, the default of every rule.

Forced deviations from the JavaScript:

* ``conditions.protocol`` is READ here; the original defined it but hard-coded ``'laser-co2'`` in the loop.
  A rule without a protocol keeps the original behaviour (``LASER_PROTOCOL_ID``).
* ``template_key`` (an addition): the approved message template a rule may send when its ``send_mode`` is not
  ``staff_task``. It is ``conditions.template_key`` when present, else the convention ``crm.<rule_key>``;
  ``clinic.message_template.template_key`` accepts dots, so a doctor-approved template named ``crm.d1`` is
  all the configuration a rule needs and no DTO of the OpenAPI changes.
* A birthday rule is always ``staff_task`` (AGENT.md: birthday messages are never sent automatically); the
  database has the same CHECK and ``validate_send_mode`` enforces it before a write.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from pema_contracts.crm import RuleKey, RuleSendMode, TaskPriority

LASER_PROTOCOL_ID = "laser-co2"
"""Protocol of the sessions that start the D+1 / D+3 / D+7 care chain and the D+30 recommendation."""

AUTOMATION_RULE_KEYS: tuple[RuleKey, ...] = (
    RuleKey.D1,
    RuleKey.D3,
    RuleKey.D7,
    RuleKey.DUE,
    RuleKey.OVERDUE,
    RuleKey.NO_SHOW,
    RuleKey.ABANDONED,
    RuleKey.DORMANT90,
    RuleKey.DORMANT180,
    RuleKey.BIRTHDAY,
)
"""The ten rules in the order of crm-data.js (``manual`` is a staff task, not a rule)."""

PROTOCOL_RULE_KEYS: frozenset[RuleKey] = frozenset({RuleKey.D1, RuleKey.D3, RuleKey.D7})
MARKETING_RULE_KEYS: frozenset[RuleKey] = frozenset({RuleKey.DORMANT90, RuleKey.DORMANT180, RuleKey.BIRTHDAY})


@dataclass(frozen=True, slots=True)
class RuleConfig:
    """One automation rule as the engine needs it (the row of ``clinic.crm_rule``)."""

    key: RuleKey
    name: str
    trigger: str
    delay_days: int
    suggested_action: str
    priority: TaskPriority
    active: bool = True
    send_mode: RuleSendMode = RuleSendMode.STAFF_TASK
    protocol: str | None = None
    marketing: bool = False
    template_key: str | None = None

    @property
    def effective_template_key(self) -> str:
        return self.template_key or f"crm.{self.key.value}"


def _row(
    key: RuleKey, name: str, trigger: str, delay_days: int, suggested_action: str, priority: TaskPriority
) -> RuleConfig:
    return RuleConfig(
        key=key,
        name=name,
        trigger=trigger,
        delay_days=delay_days,
        suggested_action=suggested_action,
        priority=priority,
        protocol=LASER_PROTOCOL_ID if key in PROTOCOL_RULE_KEYS else None,
        marketing=key in MARKETING_RULE_KEYS,
    )


DEFAULT_RULES: tuple[RuleConfig, ...] = (
    _row(
        RuleKey.D1,
        "Sau thủ thuật D+1",
        "session_completed",
        1,
        "Hỏi tình trạng sau thủ thuật",
        TaskPriority.HIGH,
    ),
    _row(
        RuleKey.D3,
        "D+3 cần ảnh",
        "session_completed",
        3,
        "Mời gửi cập nhật/ảnh có đồng ý qua Patient Mobile",
        TaskPriority.HIGH,
    ),
    _row(
        RuleKey.D7,
        "D+7 bác sĩ review",
        "session_completed",
        7,
        "Chuyển bác sĩ xem ảnh và phản hồi",
        TaskPriority.HIGH,
    ),
    _row(
        RuleKey.DUE,
        "Đến hạn tái khám",
        "expected_visit",
        0,
        "Xác nhận kế hoạch tái khám",
        TaskPriority.NORMAL,
    ),
    _row(
        RuleKey.OVERDUE,
        "Quá hạn tái khám",
        "expected_visit",
        1,
        "Hỏi trở ngại và hỗ trợ đặt lại lịch",
        TaskPriority.HIGH,
    ),
    _row(
        RuleKey.NO_SHOW,
        "Vắng/hủy chưa đặt lại",
        "appointment_missed",
        1,
        "Liên hệ hỗ trợ chọn lịch mới",
        TaskPriority.HIGH,
    ),
    _row(
        RuleKey.ABANDONED,
        "Nguy cơ bỏ liệu trình",
        "remaining_sessions",
        45,
        "Trao đổi về các buổi còn lại",
        TaskPriority.HIGH,
    ),
    _row(
        RuleKey.DORMANT90,
        "90 ngày chưa quay lại",
        "last_visit",
        90,
        "Hỏi thăm nhu cầu chăm sóc",
        TaskPriority.NORMAL,
    ),
    _row(
        RuleKey.DORMANT180,
        "180 ngày chưa quay lại",
        "last_visit",
        180,
        "Chăm sóc lại khách cũ",
        TaskPriority.HIGH,
    ),
    _row(
        RuleKey.BIRTHDAY,
        "Sinh nhật trong tuần",
        "birthday",
        7,
        "Chúc mừng sinh nhật, không gửi tự động",
        TaskPriority.LOW,
    ),
)
"""``rules`` of crm-data.js. Seeded into ``clinic.crm_rule`` for every clinic (see ``store.ensure_rules``)."""


def default_rule(key: RuleKey) -> RuleConfig:
    for rule in DEFAULT_RULES:
        if rule.key is key:
            return rule
    raise KeyError(key)


def conditions_of(rule: RuleConfig) -> dict[str, Any]:
    """``conditions`` jsonb of a rule: ``protocol`` / ``marketing`` of crm-data.js plus the template."""
    conditions: dict[str, Any] = {}
    if rule.protocol is not None:
        conditions["protocol"] = rule.protocol
    if rule.marketing:
        conditions["marketing"] = True
    if rule.template_key is not None:
        conditions["template_key"] = rule.template_key
    return conditions


def rule_from_row(
    *,
    key: RuleKey,
    name: str,
    trigger: str,
    delay_days: int,
    suggested_action: str,
    priority: TaskPriority,
    active: bool,
    send_mode: RuleSendMode,
    conditions: Mapping[str, Any],
) -> RuleConfig:
    protocol = conditions.get("protocol")
    template_key = conditions.get("template_key")
    return RuleConfig(
        key=key,
        name=name,
        trigger=trigger,
        delay_days=delay_days,
        suggested_action=suggested_action,
        priority=priority,
        active=active,
        send_mode=send_mode,
        protocol=protocol if isinstance(protocol, str) else None,
        marketing=bool(conditions.get("marketing")),
        template_key=template_key if isinstance(template_key, str) else None,
    )


def json_object(value: object) -> dict[str, Any]:
    """A jsonb value as a plain dict (anything that is not an object becomes empty)."""
    if isinstance(value, dict):
        return {str(k): v for k, v in cast(dict[Any, Any], value).items()}
    return {}


def validate_send_mode(key: RuleKey, send_mode: RuleSendMode) -> bool:
    """False for a birthday rule that is not ``staff_task`` (never automatic)."""
    return key is not RuleKey.BIRTHDAY or send_mode is RuleSendMode.STAFF_TASK
