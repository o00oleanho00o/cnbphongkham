"use client";

// Package U (step U7): puts a knowledge-base source into the staff guide (`/guide`) or takes it out, and sets its
// topic. An article is an ordinary source with the tag `guide`; the text is edited by re-adding the source, the tags
// here (`PUT /api/v1/guide/articles/{id}/tags`, audited). Needs `kb.manage`.
import { useState } from "react";

import { errorMessage, http, unwrap } from "@/lib/api/client";
import {
  draftOfTags,
  MAX_TOPIC_LENGTH,
  tagsOfDraft,
  type GuideTagsDraft,
} from "@/lib/admin/kb/kb-guide-tags";
import { Button } from "@/ui/button";
import { Dialog } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

export function KbGuideTagsModal({
  sourceId,
  sourceName,
  tags,
  onClose,
  onSaved,
}: {
  sourceId: string;
  sourceName: string;
  /** Tags the source has now (empty when it is not a guide article). */
  tags: readonly string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState<GuideTagsDraft>(() => draftOfTags(tags));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setSaving(true);
    setError("");
    try {
      await unwrap(
        http.PUT("/api/v1/guide/articles/{article_id}/tags", {
          params: { path: { article_id: sourceId } },
          body: { tags: tagsOfDraft(draft) },
        }),
      );
      onSaved();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      title="Hiện trong Hướng dẫn"
      subtitle={sourceName}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button disabled={saving} onClick={() => void save()}>
            {saving ? "Đang lưu..." : "Lưu"}
          </Button>
        </>
      }
    >
      <label className="mb-4 flex items-start gap-2.5 text-body text-ink">
        <input
          type="checkbox"
          checked={draft.guide}
          onChange={(e) => setDraft({ ...draft, guide: e.target.checked })}
          className="mt-1 h-4 w-4"
        />
        <span>
          Nhân viên đọc nguồn này ở mục <strong>Hướng dẫn</strong>
          <span className="block text-label text-ink-soft">
            Nội dung viết bằng Markdown: tiêu đề `##`, danh sách, **đậm**. Bài chỉ để đọc; sửa nội
            dung bằng cách thêm nguồn mới.
          </span>
        </span>
      </label>
      <Field
        label="Chủ đề hoặc vai trò"
        hint="Ví dụ: CSKH, Bác sĩ, Lễ tân. Dùng để nhóm và lọc bài."
        error={error === "" ? undefined : error}
      >
        {(control) => (
          <input
            {...control}
            value={draft.topic}
            maxLength={MAX_TOPIC_LENGTH}
            disabled={!draft.guide}
            onChange={(e) => setDraft({ ...draft, topic: e.target.value })}
            className={FIELD_CONTROL_CLASS}
          />
        )}
      </Field>
    </Dialog>
  );
}
