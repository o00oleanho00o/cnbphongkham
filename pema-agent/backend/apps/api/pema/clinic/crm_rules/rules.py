# ported from: prototype/shared/crm-data.js (rules)
"""The ten CRM automation rules and the configuration the engine reads.

``DEFAULT_RULES`` is the ``rules`` table of crm-data.js, row for row (id, name, trigger, delayDays,
suggestedAction, priority), with the same ``conditions``: ``protocol`` for d1/d3/d7 and ``marketing`` for
dormant90, dormant180 and birthday. ``actionType: 'staff_task'`` of the original is the only action: a rule
creates a task for the staff, nothing is sent to the patient (docs/PLAN-db-baseline.md D8).

Forced deviations from the JavaScript:

* ``conditions.protocol`` is READ here; the original defined it but hard-coded ``'laser-co2'`` in the loop.
  A rule without a protocol keeps the original behaviour (``LASER_PROTOCOL_ID``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from pema_contracts.crm import RuleKey, TaskPriority

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
    protocol: str | None = None
    marketing: bool = False


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
    """``conditions`` jsonb of a rule: ``protocol`` / ``marketing`` of crm-data.js."""
    conditions: dict[str, Any] = {}
    if rule.protocol is not None:
        conditions["protocol"] = rule.protocol
    if rule.marketing:
        conditions["marketing"] = True
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
    conditions: Mapping[str, Any],
) -> RuleConfig:
    protocol = conditions.get("protocol")
    return RuleConfig(
        key=key,
        name=name,
        trigger=trigger,
        delay_days=delay_days,
        suggested_action=suggested_action,
        priority=priority,
        active=active,
        protocol=protocol if isinstance(protocol, str) else None,
        marketing=bool(conditions.get("marketing")),
    )


def json_object(value: object) -> dict[str, Any]:
    """A jsonb value as a plain dict (anything that is not an object becomes empty)."""
    if isinstance(value, dict):
        return {str(k): v for k, v in cast(dict[Any, Any], value).items()}
    return {}
