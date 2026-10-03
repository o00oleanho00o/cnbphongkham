"use client";

// "Hướng dẫn" (old nav `guide`, prototype/shared/guide.js): how to work with Pema, organised around handoffs.
// The articles are the sources of the knowledge base that carry the tag `guide` (`GET /api/v1/guide/articles`),
// so the clinic keeps them in `/admin/kb`; here they are read only. The open article is `?a=<id>` (a child
// screen on a phone, a side pane on a desktop), like Inbox and the review queue.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { ArticleIndex } from "@/components/guide/article-index";
import { ArticleView } from "@/components/guide/article-view";
import { MasterDetail } from "@/components/ops/master-detail";
import { EmptyState, ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import { useLoad } from "@/lib/use-load";

function GuideContent() {
  const router = useRouter();
  const params = useSearchParams();
  const selectedId = params.get("a");

  const load = useCallback(
    (signal: AbortSignal) => unwrap(http.GET("/api/v1/guide/articles", { signal })),
    [],
  );
  const { data, error, loading, reload } = useLoad(load);
  const articles = data ?? [];

  const open = useCallback(
    (id: string) => router.push(`/guide?a=${encodeURIComponent(id)}`),
    [router],
  );
  const back = useCallback(() => router.push("/guide"), [router]);

  if (error) return <RetryNotice message={error} onRetry={reload} />;
  if (loading && !data) return <ListSkeleton rows={4} />;
  if (articles.length === 0) {
    return (
      <EmptyState
        title="Chưa có bài hướng dẫn nào"
        hint="Bài hướng dẫn là nguồn trong Kho tri thức có nhãn “guide”. Người có quyền quản lý kho tri thức thêm nguồn và gắn nhãn ở đó."
      />
    );
  }

  return (
    <MasterDetail
      list={<ArticleIndex articles={articles} selectedId={selectedId} onOpen={open} />}
      detailOpen={selectedId !== null}
      onBack={back}
      backLabel="Danh sách hướng dẫn"
      detail={
        selectedId ? (
          <ArticleView key={selectedId} articleId={selectedId} articles={articles} onOpen={open} />
        ) : null
      }
      emptyDetail={
        <EmptyState
          title="Chọn một chủ đề để đọc"
          hint="Mỗi bài nói rõ việc cần làm và thông tin đi tiếp như thế nào."
        />
      }
    />
  );
}

export default function GuidePage() {
  return (
    <div>
      <PageHeader
        title="Hướng dẫn sử dụng"
        subtitle="Hiểu hành trình, làm đúng bước và bàn giao đủ thông tin"
      />
      <Suspense fallback={<ListSkeleton rows={4} />}>
        <GuideContent />
      </Suspense>
    </div>
  );
}
