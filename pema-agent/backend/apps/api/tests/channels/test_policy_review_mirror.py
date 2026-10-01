"""The mirror of package P's review builders must stay equal to the owner module (``importorskip``: it activates when
``pema.policy.review`` lands in the integrated tree). Until then the mirror is pinned by its own expectations."""

from __future__ import annotations

import pytest

from pema.channels import policy_review_mirror as mirror
from pema_contracts.channel import ChannelKind
from pema_contracts.policy import DEFAULT_PROFILES, OutboundOrigin, PolicyContext, PolicyProfileKey
from pema_contracts.review import ReviewKind, ReviewOrigin
from pema_contracts.testing import FAKE_CLINIC_ID, make_inbound


def ctx() -> PolicyContext:
    return PolicyContext(
        clinic_id=FAKE_CLINIC_ID,
        account_id="zp-1",
        agent_id="a",
        channel=ChannelKind.ZALO_PERSONAL,
        thread_id="t1",
        profile=DEFAULT_PROFILES[PolicyProfileKey.PATIENT_CHANNEL],
    )


def test_job_id_on_dinh_theo_tin_khong_theo_dong_ho() -> None:
    batch = [make_inbound("a", msg_id="m1"), make_inbound("b", msg_id="m2")]
    assert mirror.red_flag_job_id(ctx(), batch) == mirror.red_flag_job_id(ctx(), batch)
    assert mirror.red_flag_job_id(ctx(), batch).startswith("policy:red_flag:zp-1:t1:")
    assert mirror.media_flag_job_id(ctx(), batch).startswith("policy:media:zp-1:t1:")
    assert mirror.red_flag_job_id(ctx(), batch) != mirror.red_flag_job_id(ctx(), batch[:1])


def test_outbound_item_dung_loai_theo_nguon_va_cat_ban_nhap_qua_dai() -> None:
    reply = mirror.build_outbound_review_item(ctx(), "xin chào", OutboundOrigin.TURN_REPLY, job_id="j1")
    follow = mirror.build_outbound_review_item(
        ctx(), "x" * 5000, OutboundOrigin.SCHEDULED_MESSAGE, job_id="j2", conversation_ref="c-1"
    )

    assert (reply.kind, reply.origin) == (ReviewKind.REPLY_DRAFT, ReviewOrigin.AGENT_TURN)
    assert (follow.kind, follow.origin) == (ReviewKind.FOLLOWUP_DRAFT, ReviewOrigin.CRM_RULE)
    assert follow.draft_text is not None
    assert len(follow.draft_text) == mirror.MAX_DRAFT_CHARS
    assert follow.payload is not None
    assert follow.payload["truncated"] is True
    assert follow.conversation_ref == "c-1"


def test_mirror_khop_voi_module_cua_goi_p() -> None:
    owner = pytest.importorskip("pema.policy.review")
    batch = [make_inbound("a", msg_id="m1", images=[])]
    assert owner.red_flag_job_id(ctx(), batch) == mirror.red_flag_job_id(ctx(), batch)
    assert owner.media_flag_job_id(ctx(), batch) == mirror.media_flag_job_id(ctx(), batch)
    assert owner.RED_FLAG_HOLDING_DRAFT == mirror.RED_FLAG_HOLDING_DRAFT
    assert owner.MEDIA_FLAG_HOLDING_DRAFT == mirror.MEDIA_FLAG_HOLDING_DRAFT
    assert owner.MAX_DRAFT_CHARS == mirror.MAX_DRAFT_CHARS
    a = owner.build_outbound_review_item(ctx(), "t", OutboundOrigin.TURN_REPLY, job_id="j")
    b = mirror.build_outbound_review_item(ctx(), "t", OutboundOrigin.TURN_REPLY, job_id="j")
    assert a == b
