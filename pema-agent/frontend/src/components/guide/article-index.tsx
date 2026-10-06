"use client";

// Index of the guide (old `.guide-index`): a search box, the topic chips and one button per article. The list is
// already loaded by the page; this component only filters and reports a choice.
import { useMemo, useState } from "react";

import { ChipRow, FilterChip } from "@/components/ops/ops-ui";
import {
  ALL_TOPICS,
  filterArticles,
  topicLabel,
  topicsOf,
  type GuideArticleSummary,
} from "@/lib/guide/guide-view";
import { FIELD_CONTROL_CLASS } from "@/ui/field";

export function ArticleIndex({
  articles,
  selectedId,
  onOpen,
}: {
  articles: readonly GuideArticleSummary[];
  selectedId: string | null;
  onOpen: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState(ALL_TOPICS);
  const topics = useMemo(() => topicsOf(articles), [articles]);
  const shown = useMemo(() => filterArticles(articles, topic, query), [articles, topic, query]);

  return (
    <div>
      <label htmlFor="guide-search" className="mb-1.5 block text-label font-semibold text-ink-soft">
        Tìm chủ đề hoặc vai trò
      </label>
      <input
        id="guide-search"
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ví dụ: dời lịch, bác sĩ, thu tiền"
        className={FIELD_CONTROL_CLASS}
      />
      {topics.length > 1 && (
        <div className="mt-3">
          <ChipRow label="Vai trò hoặc chủ đề">
            <FilterChip selected={topic === ALL_TOPICS} onClick={() => setTopic(ALL_TOPICS)}>
              Mọi chủ đề
            </FilterChip>
            {topics.map((t) => (
              <FilterChip
                key={t.topic}
                selected={topic === t.topic && topic !== ALL_TOPICS}
                count={t.count}
                onClick={() => setTopic(t.topic)}
              >
                {topicLabel(t.topic)}
              </FilterChip>
            ))}
          </ChipRow>
        </div>
      )}
      <nav aria-label="Chủ đề hướng dẫn" className="mt-4">
        {shown.length === 0 ? (
          <p className="rounded-tile border border-line bg-tile/50 px-3 py-3 text-small text-ink-soft">
            Không tìm thấy. Thử “lịch”, “thu tiền” hoặc tên vai trò.
          </p>
        ) : (
          <ul className="space-y-1">
            {shown.map((article) => (
              <li key={article.id}>
                <button
                  type="button"
                  onClick={() => onOpen(article.id)}
                  aria-current={article.id === selectedId ? "page" : undefined}
                  className={`w-full rounded-tile px-3 py-3 text-left transition-colors ${
                    article.id === selectedId
                      ? "bg-brand-50 text-brand-700"
                      : "text-ink hover:bg-tile"
                  }`}
                >
                  <span className="mb-1 block text-micro text-ink-soft">
                    {topicLabel(article.topic)}
                  </span>
                  <span className="block text-small font-semibold">{article.title}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </nav>
    </div>
  );
}
