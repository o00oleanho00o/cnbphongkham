"use client";

// One guide article: the old `.guide-article` card (topic eyebrow, title, lead, body, "Đọc tiếp"). The body is the
// Markdown of the knowledge-base source (`GET /api/v1/guide/articles/{id}`); it is shown as text, never as HTML.
import Link from "next/link";
import { useCallback } from "react";

import { ArticleBody } from "@/components/guide/article-body";
import { ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import { relatedArticles, topicLabel, type GuideArticleSummary } from "@/lib/guide/guide-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";

export function ArticleView({
  articleId,
  articles,
  onOpen,
}: {
  articleId: string;
  articles: readonly GuideArticleSummary[];
  onOpen: (id: string) => void;
}) {
  const { can } = useSession();
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/guide/articles/{article_id}", {
          params: { path: { article_id: articleId } },
          signal,
        }),
      ),
    [articleId],
  );
  const { data, error, loading, reload } = useLoad(load);

  if (error) return <RetryNotice message={error} onRetry={reload} />;
  if (loading && !data) return <ListSkeleton rows={3} />;
  if (!data) return null;

  const related = relatedArticles(articles, data.id);
  return (
    <Card>
      <article>
        <div className="flex flex-wrap items-center gap-2 text-label font-semibold tracking-wide text-ink-soft uppercase">
          {topicLabel(data.topic)}
          {data.status !== "san_sang" && <Badge tone="warning">Đang xử lý</Badge>}
        </div>
        <h2 id="guide-title" className="mt-1.5 text-title font-bold text-heading">
          {data.title}
        </h2>
        <ArticleBody markdown={data.body} />
        {related.length > 0 && (
          <footer className="mt-7 border-t border-line pt-4">
            <h3 className="mb-2.5 text-body-lg font-bold text-heading">Đọc tiếp</h3>
            <div className="flex flex-wrap gap-2">
              {related.map((article) => (
                <button
                  key={article.id}
                  type="button"
                  className={buttonClass("secondary")}
                  onClick={() => onOpen(article.id)}
                >
                  {article.title} →
                </button>
              ))}
            </div>
          </footer>
        )}
        {can("kb.manage") && (
          <p className="mt-5 text-label text-ink-soft">
            Bài này là một nguồn trong{" "}
            <Link href="/admin/kb" className="text-brand-600 underline">
              Kho tri thức
            </Link>
            : sửa nội dung và nhãn ở đó.
          </p>
        )}
      </article>
    </Card>
  );
}
