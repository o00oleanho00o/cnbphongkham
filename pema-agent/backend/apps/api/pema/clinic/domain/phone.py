"""Vietnamese phone numbers as the agent gateway stores them: digits only, from 0.

Staff enter phones free-form (``clinic.patient.phone`` is kept as typed); a number said in a chat is
normalised first, so the contact the agent saves is one the desk can dial and search. Mobiles have ten digits
(``03``, ``05``, ``07``, ``08``, ``09``), landlines eleven (``02`` and the area code).
"""

from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[\s.\-()]")
_NUMBER = re.compile(r"0[35789][0-9]{8}|02[0-9]{9}")


def normalize_vn_phone(raw: str) -> str | None:
    """``"+84 912.345.678"`` -> ``"0912345678"``; ``None`` when it is not a Vietnamese number."""
    digits = _SEPARATORS.sub("", raw.strip())
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    return digits if _NUMBER.fullmatch(digits) else None
