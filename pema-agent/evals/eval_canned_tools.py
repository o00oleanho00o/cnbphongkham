# ported from: none (stands in for the real tool bodies of src/agent/tools/*, which are package D4's)
"""Canned, SYNTHETIC tool results for the eval runner.

The original runner went through the production tool set (real ``web_search`` / ``web_fetch``), with only the
Zalo API faked. On this branch the real registry (package D4) is not present, so the runner builds the tool
set from ``FakeToolRegistry`` and gives the web tools plausible fake data instead of the trivial ``"ok"``:
with "ok" as a search result the model has nothing to open and ``tin-tuc-phai-mo-bai`` could never measure
anything.

All data is invented (``example.test`` hosts, no real people, no real news). Once package D4 is merged, pass
its registry to ``run_eval.EvalWiring.registry`` and these are not used (and ``search_probe`` can check the
real search service as the original did).
"""

from __future__ import annotations

from collections.abc import Callable

from pema_contracts.common import JsonObject

_ARTICLES: dict[str, tuple[str, str]] = {
    "https://news-1.example.test/thi-truong-a": (
        "Thị trường mẫu A tăng nhẹ phiên đầu tuần",
        "Chỉ số mẫu A tăng 0,8% lên 1.250 điểm, thanh khoản đạt 14.000 tỷ đồng (số liệu giả lập). "
        "Nhóm ngân hàng mẫu dẫn dắt đà tăng.",
    ),
    "https://news-2.example.test/thi-truong-b": (
        "Giá hàng hóa mẫu B đi ngang",
        "Giá hàng hóa mẫu B giữ ở mức 3.400 đơn vị mẫu, ít biến động so với tuần trước (số liệu giả lập).",
    ),
    "https://news-3.example.test/thi-truong-c": (
        "Tỷ giá mẫu C ổn định",
        "Tỷ giá mẫu C dao động quanh 24.000 đơn vị mẫu mỗi đô la mẫu trong biên độ hẹp (số liệu giả lập).",
    ),
}


def _web_search(args: JsonObject) -> object:
    return [{"title": title, "url": url, "snippet": body[:80]} for url, (title, body) in _ARTICLES.items()]


def _web_fetch(args: JsonObject) -> object:
    url = str(args.get("url", ""))
    article = _ARTICLES.get(url)
    if article is None:
        return {"ok": False, "loi": "Không mở được trang này (dữ liệu mẫu của eval chỉ có 3 bài)."}
    title, body = article
    return f"{title}\n\n{body}"


CANNED_RESULTS: dict[str, object | Callable[[JsonObject], object]] = {
    "web_search": _web_search,
    "web_fetch": _web_fetch,
    "save_memory": {"ok": True, "tom_tat": "Đã ghi nhớ (dữ liệu mẫu)."},
}
