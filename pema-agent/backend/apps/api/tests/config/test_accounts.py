# ported from: src/config/accounts.ts
"""``accounts.ts`` has no test file in the original; its behaviour is its docstring: no seed file is not an error,
the schema defaults, ids are kebab-case and unique. The example file of ``infra/`` must stay valid (synthetic)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pema.config.accounts import read_accounts_seed_file
from pema_contracts.policy import PolicyProfileKey

REPO_PEMA_AGENT = Path(__file__).resolve().parents[5]


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_read_accounts_seed_file_missing_file_is_none_not_an_error(tmp_path: Path) -> None:
    """null = không có file seed (cài mới hoàn toàn) - không phải lỗi"""
    assert read_accounts_seed_file(tmp_path / "khong-co.json") is None


def test_read_accounts_seed_file_applies_the_defaults_and_accepts_camel_case_keys(tmp_path: Path) -> None:
    """giá trị mặc định đúng; khóa camelCase của file gốc vẫn đọc được"""
    seed = read_accounts_seed_file(
        _write(
            tmp_path / "a.json",
            {
                "accounts": [
                    {"id": "acc-a", "label": "A"},
                    {
                        "id": "acc-b",
                        "label": "B",
                        "enabled": False,
                        "allowlist": {"mode": "list", "userIds": ["u1"]},
                        "groupRequireMention": False,
                        "policyProfile": "staff_assistant",
                    },
                ]
            },
        )
    )
    assert seed is not None
    first, second = seed
    assert (first.enabled, first.persona, first.allowlist.mode, first.allowlist.user_ids) == (
        True,
        "",
        "all",
        [],
    )
    assert (first.group_require_mention, first.respond_to_groups, first.group_passive_listen) == (
        True,
        True,
        True,
    )
    assert first.policy_profile == PolicyProfileKey.PATIENT_CHANNEL, "fail safe"
    assert (second.enabled, second.allowlist.mode, second.allowlist.user_ids) == (False, "list", ["u1"])
    assert second.group_require_mention is False
    assert second.policy_profile == PolicyProfileKey.STAFF_ASSISTANT


@pytest.mark.parametrize(
    "payload",
    [
        {"accounts": []},
        {"accounts": [{"id": "Viet Hoa", "label": "A"}]},
        {"accounts": [{"id": "acc-a", "label": ""}]},
        {"accounts": [{"id": "acc-a", "label": "A", "khong-biet": 1}]},
        {"accounts": [{"id": "acc-a", "label": "A"}, {"id": "acc-a", "label": "B"}]},
    ],
)
def test_read_accounts_seed_file_invalid_content_is_refused_as_a_whole(
    tmp_path: Path, payload: object
) -> None:
    """id sai kebab-case / nhãn rỗng / khóa lạ / id trùng: cả file bị từ chối, không tạo nửa chừng"""
    with pytest.raises(ValueError, match=r"a.json"):
        read_accounts_seed_file(_write(tmp_path / "a.json", payload))


def test_read_accounts_seed_file_not_json_is_refused(tmp_path: Path) -> None:
    """(thêm) file không phải JSON"""
    path = tmp_path / "a.json"
    path.write_text("{không phải json", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        read_accounts_seed_file(path)


def test_the_example_seed_file_in_infra_is_valid_and_synthetic() -> None:
    """(thêm) infra/accounts.example.json đọc được và chỉ chứa dữ liệu hư cấu"""
    seed = read_accounts_seed_file(REPO_PEMA_AGENT / "infra" / "accounts.example.json")
    assert seed is not None
    assert [a.id for a in seed] == ["acc-demo-bot"]
    assert all(a.policy_profile == PolicyProfileKey.PATIENT_CHANNEL for a in seed)
