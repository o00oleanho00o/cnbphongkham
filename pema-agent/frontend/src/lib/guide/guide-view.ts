// Pure helpers of the staff guide: the topic list (old `role` eyebrow of prototype/shared/guide.js) and the search
// of the index ("Tìm chủ đề hoặc vai trò": diacritics ignored, every word must appear). Articles come from the
// knowledge base (`GET /api/v1/guide/articles`).
import { foldForSearch } from "@/lib/admin/shared/fold-for-search";
import type { Schemas } from "@/lib/api";

export type GuideArticleSummary = Schemas["GuideArticleSummary"];

export const ALL_TOPICS = "";

/** Label of an article without topic. */
export const NO_TOPIC_LABEL = "Chung";

export type TopicCount = { topic: string; count: number };

/** Topics in the order they first appear in the (name ordered) list, each with how many articles it holds. */
export function topicsOf(articles: readonly GuideArticleSummary[]): TopicCount[] {
  const counts = articles.reduce<Map<string, number>>(
    (acc, article) => acc.set(article.topic, (acc.get(article.topic) ?? 0) + 1),
    new Map(),
  );
  return [...counts].map(([topic, count]) => ({ topic, count }));
}

export const topicLabel = (topic: string): string => (topic === "" ? NO_TOPIC_LABEL : topic);

function matchesQuery(article: GuideArticleSummary, query: string): boolean {
  const words = foldForSearch(query).split(/\s+/).filter(Boolean);
  const haystack = foldForSearch(`${article.title} ${article.topic} ${article.summary}`);
  return words.every((word) => haystack.includes(word));
}

/** Articles of one topic (`ALL_TOPICS` for every topic) that match the search words. */
export function filterArticles(
  articles: readonly GuideArticleSummary[],
  topic: string,
  query: string,
): GuideArticleSummary[] {
  return articles.filter(
    (article) => (topic === ALL_TOPICS || article.topic === topic) && matchesQuery(article, query),
  );
}

/** "Đọc tiếp": other articles of the same topic first, then the rest, at most `limit`, never the open one. */
export function relatedArticles(
  articles: readonly GuideArticleSummary[],
  openId: string,
  limit = 3,
): GuideArticleSummary[] {
  const open = articles.find((article) => article.id === openId);
  const others = articles.filter((article) => article.id !== openId);
  const sameTopic = others.filter((article) => article.topic === open?.topic);
  const rest = others.filter((article) => article.topic !== open?.topic);
  return [...sameTopic, ...rest].slice(0, limit);
}
