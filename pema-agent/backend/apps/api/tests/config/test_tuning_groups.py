# ported from: src/config/tuning-groups.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The group id is no longer an internal label: it is the URL segment of the Settings page (``/tuning/:group``) and
the key the browser uses to attach the non-parameter blocks to the right group. Changing an id here and
forgetting the web side breaks SILENTLY (the group loses its icon, or the LLM-provider form / password block
vanishes) with no compile error, because the two sides are joined by a string. Added: the definitions and the
specs (numbers, kinds) of package A must cover exactly the same 72 keys.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import quote

from pema.config.tuning_definitions import TUNING_DEFS, TUNING_GROUPS
from pema.config.tuning_specs import TUNING_SPECS

# Groups the web attaches its own blocks to (matches the constant of the settings page)
NHOM_CO_KHOI_RIENG = ("providers", "general")


def test_tuning_groups_id_nhom_dung_duoc_lam_doan_url() -> None:
    """id nhóm dùng được làm đoạn URL"""
    for g in TUNING_GROUPS:
        assert re.fullmatch(r"[a-z][a-z0-9-]*", g.id), f'id "{g.id}" không phải slug URL an toàn'
        assert quote(g.id, safe="") == g.id, f'id "{g.id}" phải đổi mã khi lên URL'


def test_tuning_groups_id_nhom_khong_trung_nhau() -> None:
    """id nhóm không trùng nhau"""
    ids = [g.id for g in TUNING_GROUPS]
    assert len(set(ids)) == len(ids), f"có id trùng: {', '.join(ids)}"


def test_tuning_groups_moi_tham_so_tro_toi_mot_nhom_co_that() -> None:
    """mọi tham số trỏ tới một nhóm CÓ THẬT"""
    ids = {g.id for g in TUNING_GROUPS}
    for key, d in TUNING_DEFS.items():
        assert d.group in ids, f'{key} thuộc nhóm "{d.group}" không tồn tại'


def test_tuning_groups_cac_nhom_web_gan_khoi_rieng_vao_deu_con_ton_tai() -> None:
    """các nhóm web gắn khối riêng vào đều còn tồn tại"""
    ids = {g.id for g in TUNING_GROUPS}
    for group_id in NHOM_CO_KHOI_RIENG:
        assert group_id in ids, f'mất nhóm "{group_id}" - web sẽ không hiện được khối gắn vào nó'


def test_tuning_groups_nhom_providers_co_y_khong_co_tham_so_nao_noi_dung_la_form_rieng_ben_web() -> None:
    """nhóm providers cố ý KHÔNG có tham số nào - nội dung là form riêng bên web"""
    cua = [d for d in TUNING_DEFS.values() if d.group == "providers"]
    assert len(cua) == 0, "thêm tham số vào nhóm này là sai: 4 ô nhà cung cấp phải lưu cùng lúc"


def test_tuning_groups_moi_nhom_khac_deu_co_it_nhat_mot_tham_so_nhom_rong_la_muc_nav_trong_tron() -> None:
    """mọi nhóm KHÁC đều có ít nhất một tham số - nhóm rỗng là mục nav bấm vào trống trơn"""
    dem = Counter(d.group for d in TUNING_DEFS.values())
    for g in TUNING_GROUPS:
        if g.id == "providers":
            continue
        assert dem[g.id] > 0, f'nhóm "{g.id}" không có tham số nào'


def test_tuning_groups_nhom_dau_tien_la_providers_viec_phai_lam_truoc_tien_khi_cai_moi() -> None:
    """nhóm đầu tiên là providers - việc phải làm trước tiên khi cài mới"""
    assert TUNING_GROUPS[0].id == "providers"


def test_tuning_defs_cover_exactly_the_keys_of_the_specs() -> None:
    """định nghĩa và spec của gói A phủ đúng cùng 72 khóa: thêm/bỏ một bên mà quên bên kia thì đỏ"""
    assert set(TUNING_DEFS) == set(TUNING_SPECS)
    assert len(TUNING_DEFS) == 72


def test_tuning_defs_every_entry_is_readable_by_a_person() -> None:
    """mỗi tham số có nhãn và gợi ý không rỗng; nhóm có đủ tiêu đề và nav hint"""
    for key, d in TUNING_DEFS.items():
        assert d.label.strip(), f"{key} thiếu nhãn"
        if key != "DOCUMENT_MAX_SHEETS":  # the original has an empty hint for this one (kept as is)
            assert d.hint.strip(), f"{key} thiếu gợi ý"
    for g in TUNING_GROUPS:
        assert g.title.strip()
        assert g.hint.strip()
        assert g.nav_hint.strip()


def test_tuning_defs_only_number_fields_carry_unit_presets_or_token_hint() -> None:
    """unit/presets/hienQuyDoiToken chỉ có nghĩa với ô số"""
    for key, d in TUNING_DEFS.items():
        if d.unit is not None or d.presets is not None or d.token_estimate_hint:
            assert TUNING_SPECS[key].kind == "number", (
                f"{key} không phải ô số mà có unit/presets/quy đổi token"
            )
