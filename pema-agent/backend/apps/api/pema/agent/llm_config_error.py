# ported from: src/agent/llm-config-error.ts
"""A MISSING LLM CONFIGURATION error - entirely different from an error the provider returns.

No forced deviation (``Error`` becomes ``Exception``; ``name`` is kept as an attribute so the shape-based
check works the way it did in JS).

Why a class of its own instead of a plain ``Exception``: since ``.env`` has only one mandatory variable, the
bot STARTS when the model/key/base URL are not configured (on purpose - the dashboard must be reachable to
enter them). So the "not configured yet" state is now the NORMAL state of a first install, and every
incoming message goes the whole way to ``resolve_language_model`` and then raises.

``provider_error_classifier`` only reads the HTTP code and network signs, so a plain exception falls into
``unknown`` -> the sender receives the sentence "bạn nhắn lại giúp mình sau ít phút nhé". That is a LIE:
waiting any length of time never fixes it, exactly the disease the ``auth`` branch was born to cure.

Recognised by type, NOT by scanning the words of the message - same reason as ``tool_failure_result``: a rule
based on wording means one changed word blinds the guard with no test going red.

PURE module: no import of the application.
"""

from __future__ import annotations

from typing import Literal, TypeGuard

type LoaiCauHinh = Literal["api_key", "model", "base_url"]

_TEN_LOP = "LoiCauHinhLlm"


class LoiCauHinhLlm(Exception):  # noqa: N818 - the Vietnamese name is the ported identifier
    loai_cau_hinh: LoaiCauHinh

    def __init__(self, loai_cau_hinh: LoaiCauHinh, message: str) -> None:
        super().__init__(message)
        self.name = _TEN_LOP
        self.loai_cau_hinh = loai_cau_hinh

    @staticmethod
    def is_instance(err: object) -> TypeGuard[LoiCauHinhLlm]:
        """Check by SHAPE and not a bare ``isinstance``.

        ``isinstance`` breaks when two copies of the module are in memory - it really happens with a
        dynamic ``importlib`` reload in tests. The same problem as ``APICallError.isInstance`` of the AI
        SDK.
        """
        if not err:
            return False
        return getattr(err, "name", None) == _TEN_LOP or type(err).__name__ == _TEN_LOP
