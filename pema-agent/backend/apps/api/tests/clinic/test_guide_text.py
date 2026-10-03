"""Pure text helpers of the staff guide: summary, passages and the ranking behind "Hoi Pema"."""

from __future__ import annotations

from pema.clinic.actions.guide_text import (
    PASSAGE_MAX,
    SUMMARY_MAX,
    question_words,
    rank,
    split_passages,
    summary_of,
)

ARTICLE = """Đúng người, đúng việc, đúng mốc chăm sóc.

## Cách thực hiện

1. Mở **Hôm nay**. Lọc theo trạng thái.
2. Mở một việc và ghi kết quả liên hệ.

## Điểm cần nhớ

- Khách từ chối quảng bá thì không nhận tin kết nối lại.
"""


def test_the_summary_is_the_first_paragraph_as_plain_text() -> None:
    assert summary_of(ARTICLE) == "Đúng người, đúng việc, đúng mốc chăm sóc."


def test_the_summary_skips_a_leading_heading_and_strips_markup() -> None:
    assert summary_of("# Tiêu đề\n\nMở **Hôm nay** rồi [xem](/today).\n\nĐoạn hai.") == "Mở Hôm nay rồi xem."


def test_a_long_summary_is_cut_with_an_ellipsis() -> None:
    summary = summary_of("a" * 500)
    assert len(summary) == SUMMARY_MAX
    assert summary.endswith("…")


def test_an_article_splits_into_one_passage_per_section_with_its_heading() -> None:
    passages = split_passages(ARTICLE)
    assert [p.heading for p in passages] == ["", "Cách thực hiện", "Điểm cần nhớ"]
    assert passages[0].text == "Đúng người, đúng việc, đúng mốc chăm sóc."


def test_a_long_section_is_cut_below_the_passage_ceiling() -> None:
    body = "## Dài\n\n" + "\n\n".join(f"Đoạn số {i} " + "chữ " * 60 for i in range(8))
    passages = split_passages(body)
    assert len(passages) > 1
    assert all(len(p.text) <= PASSAGE_MAX for p in passages)


def test_question_words_drop_filler_and_keep_the_topic() -> None:
    assert question_words("Làm sao để dời lịch hẹn?") == ["doi", "lich", "hen"]


def test_a_question_of_only_filler_keeps_its_words() -> None:
    assert question_words("là gì") == ["la", "gi"]


def test_ranking_ignores_diacritics_and_orders_by_relevance() -> None:
    documents = [
        "Thu tiền và kiểm tra phiếu thu",
        "Dời lịch hẹn: mở thẻ lịch rồi sửa giờ, lịch mới được lưu",
        "Bắt đầu theo vai trò",
    ]
    ranked = rank(["doi", "lich"], documents)
    assert [r.index for r in ranked] == [1]


def test_a_heading_that_names_the_topic_lifts_a_passage() -> None:
    documents = ["lịch hẹn của khách", "lịch hẹn của khách"]
    ranked = rank(["lich"], documents, titles=["Thu tiền", "Dời lịch"])
    assert [r.index for r in ranked] == [1, 0]


def test_nothing_matches_nothing() -> None:
    assert rank(["xyz"], ["Dời lịch hẹn"]) == []
    assert rank([], ["Dời lịch hẹn"]) == []
