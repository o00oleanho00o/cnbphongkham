# ported from: src/config/accounts.ts
"""Đọc config/accounts.json làm SEED cho lần chạy đầu - DB (bảng ``agent.accounts`` / ``agent.agents``) mới là
source of truth, quản lý qua dashboard. File này chỉ còn dùng khi bảng accounts trống (nâng cấp từ bản cũ
hoặc cài mới muốn khai báo sẵn).

Forced deviations: ``zod`` -> ``pydantic``; the keys keep their camelCase spelling of the original file
(``groupRequireMention``) through aliases, snake_case is accepted too. ``policy_profile`` is new and
optional (default ``patient_channel``, fail safe). No ``accounts.json`` is committed;
``infra/accounts.example.json`` is a synthetic example. The default path is ``PEMA_ACCOUNTS_SEED_FILE`` or
``config/accounts.json`` in the working directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from pema_contracts.policy import PolicyProfileKey

_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class AccountSeedAllowlist(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    mode: Literal["all", "list"] = "all"
    user_ids: list[str] = Field(default_factory=list[str], alias="userIds")


class AccountSeed(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    # id dùng làm tên thư mục data + key - giữ kebab-case
    id: str = Field(pattern=_ID_PATTERN, description="kebab-case (a-z, 0-9, dấu gạch ngang)")
    label: str = Field(min_length=1)
    enabled: bool = True
    # Bản cũ để persona trong account - migration sẽ tách thành agent riêng
    persona: str = ""
    allowlist: AccountSeedAllowlist = Field(default_factory=AccountSeedAllowlist)
    group_require_mention: bool = Field(default=True, alias="groupRequireMention")
    respond_to_groups: bool = Field(default=True, alias="respondToGroups")
    group_passive_listen: bool = Field(default=True, alias="groupPassiveListen")
    policy_profile: PolicyProfileKey = Field(default=PolicyProfileKey.PATIENT_CHANNEL, alias="policyProfile")


class AccountsSeedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accounts: list[AccountSeed] = Field(min_length=1)

    @field_validator("accounts")
    @classmethod
    def _unique_ids(cls, accounts: list[AccountSeed]) -> list[AccountSeed]:
        ids = [a.id for a in accounts]
        if len(set(ids)) != len(ids):
            raise ValueError("config/accounts.json: có account id bị trùng")
        return accounts


def default_seed_path() -> Path:
    return Path(os.environ.get("PEMA_ACCOUNTS_SEED_FILE", "config/accounts.json")).resolve()


def read_accounts_seed_file(config_path: Path | None = None) -> list[AccountSeed] | None:
    """``None`` = không có file seed (cài mới hoàn toàn) - không phải lỗi. A malformed file raises
    ``ValueError`` (the original threw): a half-read seed must stop the start-up, not create some accounts."""
    path = config_path or default_seed_path()
    if not path.exists():
        return None

    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        return AccountsSeedFile.model_validate(raw).accounts
    except json.JSONDecodeError as err:
        raise ValueError(f"{path.name}: không phải JSON hợp lệ") from err
    except ValidationError as err:
        reasons = "; ".join(str(e["msg"]) for e in err.errors(include_input=False, include_url=False))
        raise ValueError(f"{path.name}: {reasons}") from err
