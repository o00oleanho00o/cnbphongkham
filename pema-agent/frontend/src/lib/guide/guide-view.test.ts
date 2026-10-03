import { describe, expect, it } from "vitest";

import {
  ALL_TOPICS,
  filterArticles,
  relatedArticles,
  topicLabel,
  topicsOf,
  type GuideArticleSummary,
} from "./guide-view";

const article = (id: string, title: string, topic: string, summary = ""): GuideArticleSummary => ({
  id,
  title,
  topic,
  tags: topic === "" ? ["guide"] : ["guide", topic],
  summary,
  status: "san_sang",
  updated_at: "2026-09-20T09:00:00+07:00",
});

const ARTICLES = [
  article("a", "Bắt đầu theo vai trò", "Tất cả", "Biết nơi bắt đầu"),
  article("b", "CSKH chủ động", "CSKH", "Đúng người, đúng việc"),
  article("c", "Hồ sơ và Patient 360", "Bác sĩ"),
  article("d", "Thu tiền", "CSKH"),
];

describe("topicsOf", () => {
  it("counts_the_articles_of_each_topic_in_order_of_appearance", () => {
    expect(topicsOf(ARTICLES)).toEqual([
      { topic: "Tất cả", count: 1 },
      { topic: "CSKH", count: 2 },
      { topic: "Bác sĩ", count: 1 },
    ]);
  });
});

describe("topicLabel", () => {
  it("names_the_topic_of_an_untagged_article", () => {
    expect(topicLabel("")).toBe("Chung");
    expect(topicLabel("CSKH")).toBe("CSKH");
  });
});

describe("filterArticles", () => {
  it("finds_a_title_without_typing_diacritics", () => {
    expect(filterArticles(ARTICLES, ALL_TOPICS, "ho so").map((a) => a.id)).toEqual(["c"]);
  });

  it("needs_every_typed_word_somewhere_in_title_topic_or_summary", () => {
    expect(filterArticles(ARTICLES, ALL_TOPICS, "cskh dung nguoi").map((a) => a.id)).toEqual(["b"]);
  });

  it("keeps_only_the_chosen_topic", () => {
    expect(filterArticles(ARTICLES, "CSKH", "").map((a) => a.id)).toEqual(["b", "d"]);
  });

  it("lists_everything_for_an_empty_search_on_all_topics", () => {
    expect(filterArticles(ARTICLES, ALL_TOPICS, "  ")).toHaveLength(4);
  });
});

describe("relatedArticles", () => {
  it("puts_the_same_topic_first_and_leaves_out_the_open_article", () => {
    expect(relatedArticles(ARTICLES, "b").map((a) => a.id)).toEqual(["d", "a", "c"]);
  });

  it("stops_at_the_limit", () => {
    expect(relatedArticles(ARTICLES, "a", 1)).toHaveLength(1);
  });
});
