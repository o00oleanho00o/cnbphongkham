"""Staff routing: who is asked, in which order, and what happens when nobody answers (PLAN-AI01-M section 7).

New module (not a port). After the agent decides to hand off (M2b opens a ``handoff_requests`` row in
``HANDOFF_ROUTING``) this module picks the right person and moves on when she declines or is silent past the
SLA. The chain ALWAYS ends at the clinic's 24/7 on-call Zalo contact. There is no LLM anywhere in here: the
choice is a deterministic function of the request, the staff profiles, the owners of the patient and the
clock.

``build_candidates`` (in this order)
1. Outside clinic hours, a request of ``oncall_direct_from_depth`` or deeper (D3 by default) goes straight to
   the on-call contact: the chain is just ``[on_call]``.
2. Role by depth: D5 and D4 only to doctors (D5 -> any doctor on shift or the treating doctor; D4 -> the
   treating doctor or a doctor on shift); a ``required_skill`` of ``medical`` means a doctor, ``general``
   anybody, any other value must be in the profile's ``skills``.
3. People who OWN this patient come first (``patient_ownership``: the CS owner, then the treating doctor). An
   owner is not filtered by skill, shift or capacity (she knows the patient); the role rule of step 2 still
   applies to her.
4. Then everybody else who passes the role and skill rules, is on shift now and has capacity left, least
   loaded first (ties by id, so the order is deterministic). When nobody passes the skill rule the skill
   filter is dropped (a person of the right role beats nobody).
5. At most ``max_candidates`` entries in total (5 by default): up to four people, then the on-call contact,
   which is ALWAYS the last element.

``RoutingService`` (``RoutingStart`` + ``RoutingAdvance``)
* ``on_opened``: build the chain, save it into ``handoff_requests.candidates`` and ask the first one.
* ``advance``: the current candidate did not answer (SLA) or declined: ask the next one. Reaching the on-call
  contact sets ``outcome = exhausted_to_oncall`` and notifies the contact; that is the end of the chain (the
  request still waits for a staff member to ``accept`` it in the app).
* ``on_declined`` (called by ``CareControl.decline``): the reason is PII-masked and stored on the
  candidate inside ``handoff_requests.candidates`` (``export_declines`` hands them to a later, human update
  of the skill profiles; nothing here edits ``staff_profiles``). A ``suggest_user_id`` is inserted right after
  the current candidate (it must be a person who passes the role rule and has not been asked yet).
* SLA: urgent/critical 5 min, normal 30 min (``RoutingConfig``, read on every use); outside clinic hours the
  deadline is the start of the person's next shift. The deadline is handed to S as a ``SlaCheck`` (a
  scheduled job); nothing sleeps. ``on_sla_expired`` ignores a check whose candidate is no longer the current
  one, so a late or duplicated check is harmless. ``sweep_overdue`` is the backstop that finds rounds whose
  check never ran (a crash between "saved" and "scheduled") or whose chain was never built.
* Two events that move the same request at the same moment (a decline and an SLA expiry) advance it ONCE:
  ``RoutingStore.save_routing`` is a compare-and-set on ``current_idx``.

Audit lines (``agent.actions_log``): ``routing:notified:<idx>:<kind>``, ``routing:declined:<idx>:<next>``,
``routing:expired:<idx>:<next>``, ``routing:declined_queued:<idx>``, ``routing:suggested:<idx>`` and the
``oncall_used:<purpose>`` lines of ``OnCallDirectory``. Logs carry ids and codes, never a name, a phone number
or a free text.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pema.care.handoff_types import Depth
from pema.care.models import ActionDisposition, HandoffOutcome
from pema.care.oncall import PURPOSE_CHAIN, PURPOSE_NOTIFY, OnCallDirectory
from pema.care.ports import (
    HandoffRequestSnapshot,
    RoutingConfigSource,
    RoutingDirectory,
    RoutingStore,
    SendWindowProvider,
    SlaScheduler,
    StaffNotify,
)
from pema.care.routing_types import (
    DECLINE_REASON_MAX_CHARS,
    Candidate,
    CandidateKind,
    CandidateStatus,
    DeclineRecord,
    HandoffNotice,
    Ownership,
    RankReason,
    RoutingConfig,
    SlaCheck,
    StaffInfo,
    candidates_from_json,
    candidates_to_json,
)
from pema.config.runtime_tuning_settings import bot_time_zone
from pema.policy.pii import mask_pii

logger = logging.getLogger(__name__)

SWEEP_BATCH = 100
MAX_SAVE_ATTEMPTS = 3

type Clock = Callable[[], datetime]

_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


# ------------------------------------------------------------------------------------------- shifts
def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo("UTC")


def _parse_hhmm(value: object) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        hours, minutes = value.split(":")[:2]
        return time(int(hours), int(minutes))
    except ValueError:
        return None


def _shift_intervals(
    shift: Mapping[str, object], around: datetime, zone: ZoneInfo
) -> list[tuple[datetime, datetime]]:
    """Shift intervals of the days from yesterday to a week ahead, as aware datetimes. A ``["22:00",
    "06:00"]`` interval ends the next morning."""
    local = around.astimezone(zone)
    found: list[tuple[datetime, datetime]] = []
    for offset in range(-1, 9):
        day = local.date() + timedelta(days=offset)
        raw = shift.get(_DAY_KEYS[day.weekday()])
        if not isinstance(raw, list):
            continue
        for pair in raw:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(pair, list) or len(pair) != 2:  # pyright: ignore[reportUnknownArgumentType]
                continue
            start = _parse_hhmm(pair[0])  # pyright: ignore[reportUnknownArgumentType]
            end = _parse_hhmm(pair[1])  # pyright: ignore[reportUnknownArgumentType]
            if start is None or end is None or start == end:
                continue
            begin = datetime.combine(day, start, tzinfo=zone)
            finish_day = day if end > start else day + timedelta(days=1)
            found.append((begin, datetime.combine(finish_day, end, tzinfo=zone)))
    return found


def is_on_shift(shift: Mapping[str, object], now: datetime, time_zone: str) -> bool:
    return any(begin <= now < finish for begin, finish in _shift_intervals(shift, now, _zone(time_zone)))


def next_shift_start(shift: Mapping[str, object], now: datetime, time_zone: str) -> datetime | None:
    """The first shift start strictly after ``now`` (UTC); ``None`` for a profile without a shift."""
    starts = sorted(begin for begin, _ in _shift_intervals(shift, now, _zone(time_zone)) if begin > now)
    return starts[0].astimezone(UTC) if starts else None


# ---------------------------------------------------------------------------------------- the chain
def _role_allowed(info: StaffInfo, depth: Depth, required_skill: str | None, config: RoutingConfig) -> bool:
    """D4 and D5 are for doctors only; so is a request that needs the ``medical`` skill."""
    needs_doctor = depth.rank >= Depth.D4.rank or required_skill == config.medical_skill
    return info.role in config.doctor_roles if needs_doctor else True


def _skill_allowed(info: StaffInfo, required_skill: str | None, config: RoutingConfig) -> bool:
    if required_skill is None or required_skill in config.generic_skills:
        return True
    return required_skill in info.skills


def _load_key(info: StaffInfo) -> tuple[float, int, int]:
    return (info.load / info.capacity if info.capacity > 0 else 1.0, info.load, info.user_id.int)


@dataclass(frozen=True)
class RoutingOutcome:
    """What one routing step did (for tests and the dashboard)."""

    request: HandoffRequestSnapshot
    notified_idx: int
    exhausted: bool


class RoutingService:
    """``RoutingStart`` and ``RoutingAdvance`` of the care agent."""

    def __init__(
        self,
        *,
        store: RoutingStore,
        directory: RoutingDirectory,
        oncall: OnCallDirectory,
        config_source: RoutingConfigSource,
        notifier: StaffNotify,
        sla: SlaScheduler,
        window: SendWindowProvider,
        clock: Clock,
    ) -> None:
        self._store = store
        self._directory = directory
        self._oncall = oncall
        self._config = config_source
        self._notifier = notifier
        self._sla = sla
        self._window = window
        self._clock = clock

    # --------------------------------------------------------------------------------- the chain
    async def build_candidates(
        self, request: HandoffRequestSnapshot, now: datetime | None = None
    ) -> list[Candidate]:
        """The chain for ``request``. Deterministic, no LLM, and the LAST element is the on-call contact."""
        at = now if now is not None else self._clock()
        clinic_id = _clinic_of(request)
        config = await self._config.get(clinic_id)
        on_call = await self._oncall.current_on_call(clinic_id, at)
        last = Candidate(
            kind=CandidateKind.ON_CALL,
            user_id=None,
            rank_reason=RankReason.ON_CALL,
            oncall_id=on_call.id if on_call is not None else None,
        )
        depth = Depth(request.depth)
        window = await self._window.get(clinic_id)
        if not window.is_open(at) and depth.rank >= config.oncall_direct_from_depth.rank:
            return [last]

        staff = await self._directory.list_staff(clinic_id)
        owners = await self._directory.ownership(request.patient_id)
        zone = bot_time_zone()
        chosen = self._pick_staff(staff, owners, depth, request.required_skill, config, at, zone)
        if not chosen:
            chosen = self._pick_staff(
                staff, owners, depth, request.required_skill, config, at, zone, relax_skill=True
            )
        room = max(config.max_candidates - 1, 0)
        people = [
            Candidate(
                kind=CandidateKind.STAFF,
                user_id=info.user_id,
                rank_reason=reason,
                next_shift_at=next_shift_start(info.shift, at, zone),
            )
            for info, reason in chosen[:room]
        ]
        return [*people, last]

    @staticmethod
    def _pick_staff(
        staff: Sequence[StaffInfo],
        owners: Ownership,
        depth: Depth,
        required_skill: str | None,
        config: RoutingConfig,
        now: datetime,
        zone: str,
        *,
        relax_skill: bool = False,
    ) -> list[tuple[StaffInfo, RankReason]]:
        by_id = {info.user_id: info for info in staff}
        picked: list[tuple[StaffInfo, RankReason]] = []
        seen: set[UUID] = set()
        for owner_id, reason in (
            (owners.cs_owner, RankReason.CS_OWNER),
            (owners.doctor, RankReason.TREATING_DOCTOR),
        ):
            info = by_id.get(owner_id) if owner_id is not None else None
            if (
                info is not None
                and info.user_id not in seen
                and _role_allowed(info, depth, required_skill, config)
            ):
                picked.append((info, reason))
                seen.add(info.user_id)
        others = [
            info
            for info in staff
            if info.user_id not in seen
            and _role_allowed(info, depth, required_skill, config)
            and (relax_skill or _skill_allowed(info, required_skill, config))
            and info.load < info.capacity
            and is_on_shift(info.shift, now, zone)
        ]
        picked.extend((info, RankReason.ON_SHIFT) for info in sorted(others, key=_load_key))
        return picked

    # ------------------------------------------------------------------------------ the SLA
    async def _sla_due(
        self, candidate: Candidate, request: HandoffRequestSnapshot, now: datetime
    ) -> datetime:
        clinic_id = _clinic_of(request)
        config = await self._config.get(clinic_id)
        window = await self._window.get(clinic_id)
        if window.is_open(now):
            minutes = config.sla_normal_minutes if request.urgency == "normal" else config.sla_urgent_minutes
            return now + timedelta(minutes=minutes)
        if candidate.next_shift_at is not None and candidate.next_shift_at > now:
            return candidate.next_shift_at
        return window.next_open(now)

    # --------------------------------------------------------------------------- RoutingStart
    async def on_opened(self, request: HandoffRequestSnapshot, now: datetime) -> None:
        candidates = await self.build_candidates(request, now)
        if candidates[-1].oncall_id is None:
            await self._store.record_action(
                request.care_agent_id,
                action_type="routing:oncall_missing",
                disposition=ActionDisposition.PAUSED.value,
                depth=request.depth,
                at=now,
            )
        if any(c.kind is CandidateKind.ON_CALL for c in candidates):
            await self._oncall.record_use(request.care_agent_id, PURPOSE_CHAIN, request.depth, now)
        await self._activate(
            request, candidates, 0, expected_idx=request.current_idx, now=now, log="notified:0"
        )

    # -------------------------------------------------------------------------------- advancing
    async def advance(
        self,
        request: HandoffRequestSnapshot,
        now: datetime | None = None,
        *,
        status: CandidateStatus = CandidateStatus.EXPIRED,
    ) -> RoutingOutcome | None:
        """The current candidate is done (``status``): ask the next one. ``None`` when there is nothing to
        advance (the request is resolved, was moved by somebody else, or is at the on-call contact)."""
        at = now if now is not None else self._clock()
        current = await self._store.get_request(request.id)
        if current is None or current.outcome is not None:
            return None
        candidates = candidates_from_json(current.candidates)
        if not candidates:
            await self.on_opened(current, at)
            return None
        return await self._move_on(current, candidates, current.current_idx, at, status)

    async def _move_on(
        self,
        current: HandoffRequestSnapshot,
        candidates: list[Candidate],
        idx: int,
        now: datetime,
        status: CandidateStatus,
    ) -> RoutingOutcome | None:
        if candidates[idx].kind is CandidateKind.ON_CALL:
            return None
        if candidates[idx].status is not CandidateStatus.DECLINED:
            candidates[idx] = candidates[idx].with_status(status)
        nxt = idx + 1
        while nxt < len(candidates) - 1 and candidates[nxt].status in (
            CandidateStatus.DECLINED,
            CandidateStatus.EXPIRED,
        ):
            nxt += 1
        return await self._activate(
            current, candidates, nxt, expected_idx=idx, now=now, log=f"{status.value}:{idx}:{nxt}"
        )

    async def _activate(
        self,
        request: HandoffRequestSnapshot,
        candidates: list[Candidate],
        idx: int,
        *,
        expected_idx: int,
        now: datetime,
        log: str,
    ) -> RoutingOutcome | None:
        candidate = candidates[idx]
        is_on_call = candidate.kind is CandidateKind.ON_CALL
        due = None if is_on_call else await self._sla_due(candidate, request, now)
        candidates[idx] = candidate.with_status(CandidateStatus.NOTIFIED, notified_at=now, sla_due_at=due)
        saved = await self._store.save_routing(
            request.id,
            expected_idx=expected_idx,
            candidates=candidates_to_json(candidates),
            current_idx=idx,
            notified_at=now,
            outcome=HandoffOutcome.EXHAUSTED_TO_ONCALL.value if is_on_call else None,
            log_action=f"routing:{log}:{candidate.kind.value}",
            at=now,
        )
        if saved is None:
            logger.info("routing step lost a race", extra={"request_id": str(request.id)})
            return None
        notice = HandoffNotice(
            request_id=saved.id,
            patient_id=saved.patient_id,
            depth=saved.depth,
            urgency=saved.urgency,
            summary=saved.summary,
            sla_due_at=due,
            position=idx,
            is_on_call=is_on_call,
        )
        await self._deliver(saved, candidates[idx], notice, now)
        logger.info(
            "handoff routed",
            extra={"request_id": str(saved.id), "idx": idx, "kind": candidate.kind.value},
        )
        return RoutingOutcome(saved, idx, exhausted=is_on_call)

    async def _deliver(
        self, request: HandoffRequestSnapshot, candidate: Candidate, notice: HandoffNotice, now: datetime
    ) -> None:
        if candidate.kind is CandidateKind.ON_CALL:
            await self._notify_on_call(request, notice, now)
            return
        delivered = False
        if candidate.user_id is not None:
            try:
                delivered = await self._notifier.notify_staff(candidate.user_id, notice)
            except Exception as exc:  # the SLA below still moves the request on
                logger.error("staff notify raised", extra={"error": type(exc).__name__})
        if not delivered:
            await self._store.record_action(
                request.care_agent_id,
                action_type=f"routing:notify_failed:{notice.position}",
                disposition=ActionDisposition.PAUSED.value,
                depth=request.depth,
                at=now,
            )
        if notice.sla_due_at is not None:
            await self._sla.schedule_check(
                SlaCheck(
                    request_id=request.id,
                    idx=notice.position,
                    due_at=notice.sla_due_at,
                    dedupe_key=f"sla:{request.id}:{notice.position}",
                )
            )

    async def _notify_on_call(
        self, request: HandoffRequestSnapshot, notice: HandoffNotice, now: datetime
    ) -> None:
        contact = await self._oncall.current_on_call(_clinic_of(request), now)
        delivered = False
        if contact is not None:
            await self._oncall.record_use(request.care_agent_id, PURPOSE_NOTIFY, request.depth, now)
            try:
                delivered = await self._notifier.notify_on_call(contact, notice)
            except Exception as exc:
                logger.error("on-call notify raised", extra={"error": type(exc).__name__})
        if not delivered:
            logger.error("the on-call contact could not be notified", extra={"request_id": str(request.id)})
            await self._store.record_action(
                request.care_agent_id,
                action_type="routing:oncall_notify_failed",
                disposition=ActionDisposition.PAUSED.value,
                depth=request.depth,
                at=now,
            )

    # ------------------------------------------------------------------------------ SLA expiry
    async def on_sla_expired(
        self, request_id: UUID, idx: int, now: datetime | None = None
    ) -> RoutingOutcome | None:
        """The scheduled ``SlaCheck`` of candidate ``idx`` fired. A check for a candidate that is no longer
        the current one (accepted, declined, already moved on) does nothing."""
        at = now if now is not None else self._clock()
        current = await self._store.get_request(request_id)
        if current is None or current.outcome is not None or current.current_idx != idx:
            return None
        candidates = candidates_from_json(current.candidates)
        if idx >= len(candidates):
            return None
        due = candidates[idx].sla_due_at
        if due is not None and at < due:  # fired early: look again at the deadline
            await self._sla.schedule_check(
                SlaCheck(request_id=request_id, idx=idx, due_at=due, dedupe_key=f"sla:{request_id}:{idx}")
            )
            return None
        return await self._move_on(current, candidates, idx, at, CandidateStatus.EXPIRED)

    async def sweep_overdue(self, now: datetime | None = None, *, limit: int = SWEEP_BATCH) -> int:
        """Backstop for a check that never ran: advance every waiting request whose current candidate is past
        its deadline, and build the chain of a request that has none. Returns how many were touched."""
        at = now if now is not None else self._clock()
        touched = 0
        for request in await self._store.list_unresolved_requests(limit=limit):
            candidates = candidates_from_json(request.candidates)
            if not candidates:
                await self.on_opened(request, at)
                touched += 1
                continue
            idx = request.current_idx
            if idx < len(candidates):
                due = candidates[idx].sla_due_at
                if (
                    due is not None
                    and due <= at
                    and await self.on_sla_expired(request.id, idx, at) is not None
                ):
                    touched += 1
        return touched

    # ---------------------------------------------------------------------------- RoutingAdvance
    async def on_declined(
        self,
        request: HandoffRequestSnapshot,
        staff_id: UUID,
        reason: str,
        suggest_user_id: UUID | None,
    ) -> None:
        masked = mask_pii(reason.strip()).text.strip()[:DECLINE_REASON_MAX_CHARS]
        for _ in range(MAX_SAVE_ATTEMPTS):
            at = self._clock()
            current = await self._store.get_request(request.id)
            if current is None or current.outcome is not None:
                return
            candidates = candidates_from_json(current.candidates)
            pos = _position_of(candidates, staff_id)
            if pos is None:
                await self._store.record_action(
                    current.care_agent_id,
                    action_type="routing:declined_outside_chain",
                    disposition=ActionDisposition.PAUSED.value,
                    depth=current.depth,
                    at=at,
                )
                return
            candidates[pos] = candidates[pos].with_status(
                CandidateStatus.DECLINED, declined_at=at, decline_reason=masked or None
            )
            if suggest_user_id is not None:
                candidates = await self._insert_suggested(current, candidates, suggest_user_id, at)
            if pos == current.current_idx:
                if await self._move_on(current, candidates, pos, at, CandidateStatus.DECLINED) is not None:
                    return
                continue
            saved = await self._store.save_routing(
                current.id,
                expected_idx=current.current_idx,
                candidates=candidates_to_json(candidates),
                current_idx=current.current_idx,
                notified_at=current.current_notified_at,
                outcome=None,
                log_action=f"routing:declined_queued:{pos}",
                at=at,
            )
            if saved is not None:
                return

    async def _insert_suggested(
        self,
        request: HandoffRequestSnapshot,
        candidates: list[Candidate],
        user_id: UUID,
        now: datetime,
    ) -> list[Candidate]:
        """Put the suggested person right after the current candidate, if she may be asked at all."""
        clinic_id = _clinic_of(request)
        config = await self._config.get(clinic_id)
        info = next((s for s in await self._directory.list_staff(clinic_id) if s.user_id == user_id), None)
        if info is None or not _role_allowed(info, Depth(request.depth), request.required_skill, config):
            logger.info("suggested person ignored", extra={"request_id": str(request.id)})
            return candidates
        existing = _position_of(candidates, user_id)
        if existing is not None and candidates[existing].status is not CandidateStatus.PENDING:
            return candidates  # already asked (or the one who answers now): never twice
        if existing is not None:
            del candidates[existing]
        suggested = Candidate(
            kind=CandidateKind.STAFF,
            user_id=user_id,
            rank_reason=RankReason.SUGGESTED,
            next_shift_at=next_shift_start(info.shift, now, bot_time_zone()),
        )
        at_idx = min(request.current_idx + 1, len(candidates) - 1)
        candidates.insert(at_idx, suggested)
        return candidates

    # ----------------------------------------------------------------------------------- export
    async def export_declines(self, since: datetime, *, limit: int = 1000) -> Sequence[DeclineRecord]:
        """Decline reasons for the later (human) update of the skill profiles. Read only."""
        return await self._store.declines_since(since, limit=limit)


def _position_of(candidates: Sequence[Candidate], user_id: UUID) -> int | None:
    for position, candidate in enumerate(candidates):
        if candidate.kind is CandidateKind.STAFF and candidate.user_id == user_id:
            return position
    return None


def _clinic_of(request: HandoffRequestSnapshot) -> UUID:
    if request.clinic_id is None:
        raise ValueError("the handoff request has no clinic id")
    return request.clinic_id
