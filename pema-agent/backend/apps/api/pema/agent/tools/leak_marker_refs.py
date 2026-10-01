# ported from: src/agent/prompt-leak-markers.ts (only THE_NOI_DUNG_NGOAI)
"""The one marker constant the tool layer needs from ``prompt-leak-markers``.

Must equal ``pema.agent.prompt_leak_markers.THE_NOI_DUNG_NGOAI`` (package D1); package G replaces this module
with the import. Until D1 lands, ``wrap_untrusted_content`` takes the value from here, and
``test_wrap_untrusted_content`` checks the equality as soon as the D1 module exists.
"""

from __future__ import annotations

THE_NOI_DUNG_NGOAI = "noi_dung_ngoai"
"""Tên thẻ GỐC (không nonce) bọc nội dung lấy từ nguồn ngoài; dùng chung với bộ canh rò prompt, bộ canh chỉ
neo TIỀN TỐ (``<noi_dung_ngoai``) nên hậu tố nonce thêm vào không đòi sửa gì ở đó."""
