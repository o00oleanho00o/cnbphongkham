# ported from: none (src/agent/mid-turn-injection.ts has no test of its own in zalo-agent; its wiring is
# covered by the injection cases of run-agent-turn.test.ts, see ``test_run_agent_turn``)
"""Unit tests of ``mid_turn_injection``: the label, the build of the injected message, the image-free rebuild
when it is over budget, and ``tao_bo_chen_tin`` (the ``prepare_step`` function): every branch that must return
``None`` (no change) instead of killing the running turn.

Test names are descriptive (no original ``describe_it`` exists); the Vietnamese rule they pin is in the
docstring.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from pema.agent.agent_turn_content import TurnContentDeps
from pema.agent.history_to_model_messages import StoredImage
from pema.agent.mid_turn_injection import (
    NHAN_TIN_CHEN,
    TY_LE_TRAN_TIN_CHEN,
    dung_tin_chen,
    dung_tin_chen_trong_ngan_sach,
    tao_bo_chen_tin,
)
from pema.agent.model_types import ModelMessage
from pema.agent.testing_conversation import FakeConversation
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.channel import InboundImage, InboundMessage
from pema_contracts.testing import FAKE_CLINIC_ID, make_inbound

PNG_B64 = "iVBORw0KGgoAAAABAAAAAQCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


@pytest.fixture(autouse=True)
def tuning() -> Iterator[None]:
    install_tuning_provider(StaticTuningProvider({}))
    yield
    reset_tuning_provider()


def make_deps(images: dict[str, StoredImage] | None = None) -> TurnContentDeps:
    store = images or {}

    async def download(_url: str) -> StoredImage | None:
        return None

    return TurnContentDeps(
        clinic_id=FAKE_CLINIC_ID,
        load_image=store.get,
        download_image=download,
        image_descriptions=FakeConversation(),
    )


def msg(text: str, **extra: Any) -> InboundMessage:
    return make_inbound(text, account_id="acc", thread_id="t1", sender_id="u1", sender_name="Hải", **extra)


class Guard:
    def __init__(self) -> None:
        self.resets = 0

    def dat_lai(self) -> None:
        self.resets += 1


def make_injector(
    fetch: object,
    *,
    guard: Guard | None = None,
    deps: TurnContentDeps | None = None,
    image_mode: str = "blind",
    ceiling: int = 100_000,
):  # type: ignore[no-untyped-def]
    return tao_bo_chen_tin(
        lay_tin_chen=fetch,  # type: ignore[arg-type]
        lay_image_mode=lambda: image_mode,  # type: ignore[arg-type,return-value]
        lay_tran_token=lambda: ceiling,
        guard=guard or Guard(),
        deps=deps or make_deps(),
    )


def texts(message: ModelMessage) -> list[str]:
    return [p["text"] for p in message["content"] if p.get("type") == "text"]


async def test_dung_tin_chen_nhan_dung_dau_roi_den_noi_dung_cua_tin() -> None:
    """the label comes first (it says "đang làm dở"), then the content of each injected message"""
    out = await dung_tin_chen([msg("làm thêm cột giá nhé")], "blind", deps=make_deps())

    assert out["role"] == "user"
    parts = out["content"]
    assert parts[0] == {"type": "text", "text": NHAN_TIN_CHEN}
    assert "đang làm dở" in NHAN_TIN_CHEN
    assert any("làm thêm cột giá nhé" in t for t in texts(out))


async def test_dung_tin_chen_nhan_khong_boc_trong_the_noi_dung_ngoai() -> None:
    """a real person's words are NOT wrapped as external data (the model would learn to ignore them)"""
    out = await dung_tin_chen([msg("sửa lại giúp mình")], "blind", deps=make_deps())
    assert "noi_dung_ngoai" not in "".join(texts(out))


async def test_dung_tin_chen_trong_ngan_sach_tin_nho_thi_giu_nguyen() -> None:
    """a small message is kept as built, in the mode it was asked for"""
    out = await dung_tin_chen_trong_ngan_sach([msg("thêm một dòng")], "blind", 100_000, deps=make_deps())
    assert any("thêm một dòng" in t for t in texts(out))


async def test_dung_tin_chen_trong_ngan_sach_qua_tran_thi_dung_lai_khong_anh_nhung_giu_chu() -> None:
    """over the budget (8 pictures in native mode): rebuilt WITHOUT images, the text is kept"""
    images = {f"m/{i}.png": StoredImage(base64=PNG_B64, media_type="image/png") for i in range(8)}
    tin = msg(
        "xem giúp 8 ảnh này",
        images=[InboundImage(url=f"http://x/{i}.png", local_path=f"m/{i}.png") for i in range(8)],
    )
    deps = make_deps(images)

    native = await dung_tin_chen([tin], "native", deps=deps)
    assert sum(1 for p in native["content"] if p.get("type") == "file") == 8, "precondition: 8 pixel blocks"

    # a ceiling so small that 25 percent of it cannot hold eight images
    rebuilt = await dung_tin_chen_trong_ngan_sach([tin], "native", 4_000, deps=deps)
    assert not any(p.get("type") == "file" for p in rebuilt["content"])
    assert any("xem giúp 8 ảnh này" in t for t in texts(rebuilt))
    assert TY_LE_TRAN_TIN_CHEN == 0.25


async def test_tao_bo_chen_tin_khong_co_nguon_tin_thi_khong_doi_gi() -> None:
    """a scheduled turn passes no source: the path is off"""
    chen = make_injector(None)
    assert await chen([{"role": "user", "content": "x"}]) is None


async def test_tao_bo_chen_tin_tat_bang_tuning_thi_khong_goi_nguon_tin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``MID_TURN_INJECTION_ENABLED`` false: the source is not even asked"""
    install_tuning_provider(StaticTuningProvider({"MID_TURN_INJECTION_ENABLED": False}))
    asked = 0

    async def fetch() -> Sequence[InboundMessage]:
        nonlocal asked
        asked += 1
        return [msg("tin mới")]

    assert await make_injector(fetch)([]) is None
    assert asked == 0


async def test_tao_bo_chen_tin_khong_co_tin_moi_thi_khong_doi_va_khong_reset_guard() -> None:
    """nothing new: no change and the guard counters stay (they belong to the unchanged direction)"""
    guard = Guard()

    async def fetch() -> Sequence[InboundMessage]:
        return []

    assert await make_injector(fetch, guard=guard)([]) is None
    assert guard.resets == 0


async def test_tao_bo_chen_tin_co_tin_moi_thi_them_vao_cuoi_va_reset_guard() -> None:
    """a new message is APPENDED after the current messages and resets the tool-loop guard (new context must
    not carry the sins of the part before it)"""
    guard = Guard()
    current: list[ModelMessage] = [{"role": "user", "content": "yêu cầu đầu"}]

    async def fetch() -> Sequence[InboundMessage]:
        return [msg("đổi sang bảng 3 cột")]

    out = await make_injector(fetch, guard=guard)(current)

    assert out is not None
    assert out[:-1] == current
    assert out[-1]["role"] == "user"
    assert any("đổi sang bảng 3 cột" in t for t in texts(out[-1]))
    assert guard.resets == 1
    assert len(current) == 1, "the input list is not mutated"


async def test_tao_bo_chen_tin_nguon_tin_hong_thi_bo_qua_khong_giet_luot_dang_chay() -> None:
    """a broken queue returns None instead of raising: skipping the insertion beats losing the answer"""
    guard = Guard()

    async def fetch() -> Sequence[InboundMessage]:
        raise RuntimeError("queue down")

    assert await make_injector(fetch, guard=guard)([{"role": "user", "content": "x"}]) is None
    assert guard.resets == 0


async def test_tao_bo_chen_tin_image_mode_doc_lai_moi_lan_vi_no_doi_giua_luot() -> None:
    """``lay_image_mode`` is a function: after the loop dropped pixels the NEXT injection is built blind"""
    images = {"m/0.png": StoredImage(base64=PNG_B64, media_type="image/png")}
    tin = msg("ảnh này", images=[InboundImage(url="http://x/0.png", local_path="m/0.png")])
    mode = {"value": "native"}

    async def fetch() -> Sequence[InboundMessage]:
        return [tin]

    chen = tao_bo_chen_tin(
        lay_tin_chen=fetch,
        lay_image_mode=lambda: mode["value"],  # type: ignore[arg-type,return-value]
        lay_tran_token=lambda: 100_000,
        guard=Guard(),
        deps=make_deps(images),
    )

    first = await chen([])
    mode["value"] = "blind"
    second = await chen([])

    assert first is not None
    assert second is not None
    assert any(p.get("type") == "file" for p in first[-1]["content"])
    assert not any(p.get("type") == "file" for p in second[-1]["content"])
