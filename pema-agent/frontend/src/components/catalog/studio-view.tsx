"use client";

// Before / After Studio of one patient (`GET /api/v1/studio/{patient_id}?view=`). Old web: `clinic.js` `studio()` and
// `photos()` (design spec I7): pick a view (Chính diện, Má trái, Má phải), see the first photo as "Trước" and the
// latest as "Sau" side by side or with a comparison slider, zoom, and read the metadata and the notice that the
// alignment is not checked and nothing medical may be read from the images. No image is analysed or aligned.
//
// The photo store belongs to the Patient 360 step; until it exists the backend sends no photo and the screen shows
// the clinic's illustrative placeholders, as the old web did for a patient with no upload. "Thêm ảnh" opens the
// patient's record, where a photo is attached to a session together with the consent.
import Link from "next/link";
import { useCallback, useState } from "react";

import { ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import {
  STUDIO_ALIGNMENT_NOTICE,
  STUDIO_NO_MEDICAL_READING,
  studioMetadata,
} from "@/lib/catalog/catalog-view";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button, buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

type Mode = "side" | "slider";

/** Synthetic face outline: stands in for a photo and says so in its label. */
function FacePlaceholder({ stage }: { stage: "before" | "after" }) {
  return (
    <svg
      viewBox="0 0 200 240"
      role="img"
      aria-label={`Ảnh minh họa tổng hợp (${stage === "before" ? "trước" : "sau"})`}
      className="block h-auto max-h-[470px] w-full bg-tile"
    >
      <ellipse
        cx="100"
        cy="112"
        rx="52"
        ry="68"
        className="fill-brand-100 stroke-brand-500"
        strokeWidth="2"
      />
      <ellipse cx="80" cy="102" rx="6" ry="3.5" className="fill-brand-500" />
      <ellipse cx="120" cy="102" rx="6" ry="3.5" className="fill-brand-500" />
      <path d="M100 108v22l-7 6" className="fill-none stroke-brand-500" strokeWidth="2" />
      <path d="M84 150q16 12 32 0" className="fill-none stroke-brand-500" strokeWidth="2" />
      {stage === "before" && (
        <g className="fill-brand-500" opacity="0.35">
          <circle cx="82" cy="124" r="5" />
          <circle cx="118" cy="122" r="6" />
          <circle cx="104" cy="90" r="4" />
        </g>
      )}
      <path
        d="M32 232c8-44 36-56 68-56s60 12 68 56"
        className="fill-brand-100 stroke-brand-500"
        strokeWidth="2"
      />
    </svg>
  );
}

function Tile({ label, stage }: { label: string; stage: "before" | "after" }) {
  return (
    <figure className="min-w-0 overflow-hidden rounded-tile border border-line">
      <figcaption className="border-b border-line bg-surface px-3 py-1.5 text-label font-semibold text-ink-soft">
        {label}
      </figcaption>
      <FacePlaceholder stage={stage} />
    </figure>
  );
}

export function StudioView({
  patientId,
  view,
  onView,
}: {
  patientId: string;
  view: string;
  onView: (v: string) => void;
}) {
  const [mode, setMode] = useState<Mode>("side");
  const [zoom, setZoom] = useState(1);
  const [split, setSplit] = useState(50);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/studio/{patient_id}", {
          params: { path: { patient_id: patientId }, query: { view } },
          signal,
        }),
      ),
    [patientId, view],
  );
  const { data, error, loading, reload } = useLoad(load);

  if (error) return <RetryNotice message={error} onRetry={reload} />;
  if (!data) return loading ? <ListSkeleton rows={3} /> : null;

  const hasPhotos = data.photos.length > 0;
  return (
    <Card
      title="Before / After Studio"
      subtitle={`${data.patient_name} · ${data.patient_code}${data.concern ? ` · ${data.concern}` : ""}`}
      aside={
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Góc ảnh so sánh"
            value={data.view}
            onChange={(e) => onView(e.target.value)}
            className={cx(FIELD_BASE_CLASS, "min-h-10")}
          >
            {data.views.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <Button variant="secondary" onClick={() => setMode(mode === "side" ? "slider" : "side")}>
            {mode === "side" ? "So sánh trượt" : "Đặt cạnh nhau"}
          </Button>
          <Link href={`/patients/${data.patient_id}`} className={buttonClass("primary")}>
            ＋ Thêm ảnh
          </Link>
        </div>
      }
    >
      <div className="mb-3">
        <Notice>
          {hasPhotos
            ? `${data.photos.length} ảnh gắn với buổi điều trị, lọc cùng góc khai báo: ${data.view}. `
            : "Chưa có ảnh upload ở góc này. Hai ảnh dưới đây là minh họa tổng hợp. "}
          {STUDIO_ALIGNMENT_NOTICE}
        </Notice>
      </div>

      <div className="overflow-hidden">
        {mode === "side" ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="origin-center" style={{ transform: `scale(${zoom})` }}>
              <Tile label={hasPhotos ? "Trước" : "MINH HỌA TRƯỚC"} stage="before" />
            </div>
            <div className="origin-center" style={{ transform: `scale(${zoom})` }}>
              <Tile label={hasPhotos ? "Sau" : "MINH HỌA SAU"} stage="after" />
            </div>
          </div>
        ) : (
          <div className="relative mx-auto max-w-[650px] overflow-hidden rounded-tile border border-line">
            <div className="origin-center" style={{ transform: `scale(${zoom})` }}>
              <FacePlaceholder stage="after" />
            </div>
            <div
              className="pointer-events-none absolute inset-0 origin-center"
              style={{ clipPath: `inset(0 ${100 - split}% 0 0)`, transform: `scale(${zoom})` }}
            >
              <FacePlaceholder stage="before" />
            </div>
            <span className="absolute top-3 left-3">
              <Badge tone="neutral" dot={false}>
                Trước ← → Sau
              </Badge>
            </span>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-label text-ink-soft">
        <label className="inline-flex items-center gap-2">
          Phóng to
          <input
            type="range"
            min={1}
            max={2}
            step={0.1}
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            aria-label="Phóng to ảnh"
          />
        </label>
        {mode === "slider" ? (
          <label className="inline-flex items-center gap-2">
            Vị trí so sánh
            <input
              type="range"
              min={0}
              max={100}
              value={split}
              onChange={(e) => setSplit(Number(e.target.value))}
              aria-label="Vị trí đường so sánh"
            />
          </label>
        ) : (
          <Badge tone="neutral" dot={false}>
            Cùng góc khai báo · không tự căn chỉnh
          </Badge>
        )}
      </div>

      <div className="mt-3 space-y-2">
        <Notice tone={data.media_consent ? "success" : "warn"}>
          {studioMetadata(data.view, data.media_consent, hasPhotos)} {STUDIO_NO_MEDICAL_READING}
        </Notice>
        {!data.media_consent && (
          <Notice tone="warn">
            Chưa có đồng ý sử dụng ảnh. Cần ghi nhận đồng ý trong hồ sơ trước khi lưu ảnh mốc.
          </Notice>
        )}
      </div>
    </Card>
  );
}
