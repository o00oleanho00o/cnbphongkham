"use client";

// "Hỏi Pema" (old nav `ask`): a question box over the staff guide. The answer is the passages of the guide
// articles that match (`POST /api/v1/guide/ask`): retrieval, nothing is generated, so it cannot invent a rule.
// There is no HTTP chat with the staff_assistant agent in the backend (that agent talks over Zalo); a chat with a
// model would be a new agent entry and is not part of this step. The conversation lives in this page only.
import Link from "next/link";
import { useCallback, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { ArticleBody } from "@/components/guide/article-body";
import { Notice, Spinner } from "@/components/ops/ops-ui";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import {
  answeredTurn,
  askedTurn,
  cleanQuestion,
  failedTurn,
  MAX_QUESTION_LENGTH,
  SUGGESTED_QUESTIONS,
  type AskTurn,
} from "@/lib/guide/ask-thread";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { FIELD_CONTROL_CLASS } from "@/ui/field";

function Answer({ turn }: { turn: AskTurn }) {
  if (turn.state === "loading") return <Spinner label="Đang tìm trong hướng dẫn" />;
  if (turn.state === "error") {
    return <Notice tone="error">{turn.error} Hãy thử lại sau ít phút.</Notice>;
  }
  if (turn.hits.length === 0) {
    return (
      <p className="text-body text-ink-soft">
        Chưa thấy nội dung này trong hướng dẫn. Thử từ khóa khác, hoặc hỏi quản lý phòng khám.
      </p>
    );
  }
  return (
    <ol className="space-y-3">
      {turn.hits.map((hit, index) => (
        <li key={`${hit.article_id}-${hit.heading}-${index}`}>
          <Card padded={false} className="px-4 py-3">
            <p className="text-label text-ink-soft">
              <Link
                href={`/guide?a=${encodeURIComponent(hit.article_id)}`}
                className="font-semibold text-brand-600 underline"
              >
                {hit.article_title}
              </Link>
              {hit.heading !== "" && <span> · {hit.heading}</span>}
            </p>
            <ArticleBody markdown={hit.passage} />
          </Card>
        </li>
      ))}
    </ol>
  );
}

export default function AskPage() {
  const [turns, setTurns] = useState<readonly AskTurn[]>([]);
  const [draft, setDraft] = useState("");
  const nextId = useRef(1);

  const ask = useCallback(async (raw: string) => {
    const question = cleanQuestion(raw);
    if (question === "") return;
    const id = nextId.current;
    nextId.current += 1;
    setDraft("");
    setTurns((current) => askedTurn(current, id, question));
    try {
      // POST so the question stays out of the URL (access logs); the call changes nothing.
      const reply = await unwrap(http.POST("/api/v1/guide/ask", { body: { question } }));
      setTurns((current) => answeredTurn(current, id, reply.hits));
    } catch (e) {
      setTurns((current) => failedTurn(current, id, errorMessage(e)));
    }
  }, []);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void ask(draft);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void ask(draft);
  };

  return (
    <div>
      <PageHeader
        title="Hỏi Pema"
        subtitle="Hỏi nhanh cách làm việc; câu trả lời lấy từ các bài hướng dẫn của phòng khám"
      />
      <div className="mb-4">
        <Notice>
          Đây là tìm trong hướng dẫn nội bộ, không phải tư vấn y khoa. Đừng nhập tên hay thông tin
          của bệnh nhân vào ô hỏi.
        </Notice>
      </div>

      <div className="mx-auto max-w-3xl">
        {turns.length === 0 && (
          <div className="mb-5">
            <p className="mb-2 text-label font-semibold text-ink-soft">Gợi ý</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED_QUESTIONS.map((question) => (
                <Button key={question} variant="secondary" onClick={() => void ask(question)}>
                  {question}
                </Button>
              ))}
            </div>
          </div>
        )}

        <div aria-live="polite" className="space-y-5">
          {turns.map((turn) => (
            <section key={turn.id} aria-label={`Câu hỏi: ${turn.question}`}>
              <p className="ml-auto w-fit max-w-[90%] rounded-card bg-brand-500 px-4 py-2.5 text-body text-surface">
                {turn.question}
              </p>
              <div className="mt-2.5">
                <Answer turn={turn} />
              </div>
            </section>
          ))}
        </div>

        <form onSubmit={onSubmit} className="mt-6 bg-canvas py-3 lg:sticky lg:bottom-0">
          <label htmlFor="ask-input" className="sr-only">
            Câu hỏi
          </label>
          <div className="flex items-end gap-2">
            <textarea
              id="ask-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              rows={2}
              maxLength={MAX_QUESTION_LENGTH}
              placeholder="Ví dụ: làm sao dời lịch hẹn?"
              className={`${FIELD_CONTROL_CLASS} resize-none`}
            />
            <Button type="submit" disabled={cleanQuestion(draft) === ""}>
              Hỏi
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
