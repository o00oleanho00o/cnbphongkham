# ported from: src/zalo/reaction-icons.ts
"""Danh sách reaction cho auto-react. Key ngắn (lưu DB + gửi qua API) map sang enum của zca-js. Dùng chung với
tool add_reaction để agent và auto-react nói cùng một ngôn ngữ.

Forced deviation: zca-js (and its ``Reactions`` enum) lives in the Node bridge. ``zalo`` is therefore the
wire key
sent to the bridge (equal to the short key); the bridge maps it to the zca-js ``Reactions`` value
(``backend/bridges/zalo-personal/src/reaction-icons.ts``, same keys, unknown key falls back to heart).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReactionIcon:
    zalo: str
    emoji: str
    label: str


REACTION_ICONS: dict[str, ReactionIcon] = {
    "heart": ReactionIcon(zalo="heart", emoji="❤️", label="Tim"),
    "like": ReactionIcon(zalo="like", emoji="👍", label="Thích"),
    "haha": ReactionIcon(zalo="haha", emoji="😆", label="Haha"),
    "wow": ReactionIcon(zalo="wow", emoji="😮", label="Wow"),
    "ok": ReactionIcon(zalo="ok", emoji="👌", label="OK"),
    "rose": ReactionIcon(zalo="rose", emoji="🌹", label="Hoa hồng"),
    "kiss": ReactionIcon(zalo="kiss", emoji="😘", label="Hôn"),
    "cry": ReactionIcon(zalo="cry", emoji="😢", label="Buồn"),
    "angry": ReactionIcon(zalo="angry", emoji="😠", label="Giận"),
}

REACTION_ICON_KEYS: tuple[str, ...] = tuple(REACTION_ICONS)


def is_reaction_icon_key(value: str) -> bool:
    return value in REACTION_ICONS


def to_zalo_reaction(key: str) -> str:
    """Icon lạ (DB cũ, người sửa tay) rơi về tim thay vì làm hỏng lượt xử lý."""
    return (REACTION_ICONS[key] if is_reaction_icon_key(key) else REACTION_ICONS["heart"]).zalo
