"use client";

// Ảnh trước / sau tab: the clinical photos of the patient in a grid by stage, the consent they rest on, and the
// upload. Photos are shown and stored, never analysed and never compared automatically (PLAN-AI01-U principle 6).
// The images come from `GET /media/{id}/content`, which the BE audits and which needs the patient's consent for
// care staff. Source: `photos` of prototype/shared/clinic.js (stage, angle filter, metadata line).
import { useCallback, useRef, useState, type FormEvent } from "react";

import { FormError, Muted, TwoCol } from "@/components/ops/patient/shared";
import { ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/ops/format";
import { MEDIA_STAGE_LABEL, PHOTO_REGIONS, PHOTO_VIEWS } from "@/lib/ops/labels";
import { checkPhotoFile, uploadPhoto } from "@/lib/ops/media-upload";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Dialog } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Media = Schemas["MediaOut"];
type Stage = Schemas["MediaStage"];

const STAGES: readonly Stage[] = ["before", "after"];
const ALL_VIEWS = "all";

function captionOf(media: Media): string {
  const where = [media.region, media.view].filter((part): part is string => !!part).join(" · ");
  return `${formatDate(media.created_at)}${where === "" ? "" : ` · ${where}`}`;
}

function altOf(media: Media): string {
  return `Ảnh ${MEDIA_STAGE_LABEL[media.stage].toLowerCase()}, ${captionOf(media)}`;
}

function PhotoTile({ media, onOpen }: { media: Media; onOpen: () => void }) {
  return (
    <li className="min-w-0">
      <button
        type="button"
        onClick={onOpen}
        className="block w-full overflow-hidden rounded-control border border-line bg-tile text-left hover:border-brand-500"
        aria-label={`Xem ảnh: ${captionOf(media)}`}
      >
        {/* The image is a same-origin, cookie-authenticated stream: next/image cannot fetch it. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={media.content_path}
          alt={altOf(media)}
          loading="lazy"
          className="aspect-[4/5] w-full object-cover"
        />
        <span className="block px-2 py-1.5 text-label break-words text-ink-soft">
          {captionOf(media)}
        </span>
      </button>
    </li>
  );
}

export function PhotosTab({
  patientId,
  consentGranted,
  canUpload,
  canRecordConsent,
  onChanged,
}: {
  patientId: string;
  /** The patient's current media consent is a grant. */
  consentGranted: boolean;
  /** `media.write`. */
  canUpload: boolean;
  /** `consent.write`: may record the consent from here. */
  canRecordConsent: boolean;
  onChanged: () => void;
}) {
  const toast = useToast();
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients/{patient_id}/media", {
          params: { path: { patient_id: patientId } },
          signal,
        }),
      ),
    [patientId],
  );
  const { data, error, loading, reload } = useLoad(load);
  const [view, setView] = useState(ALL_VIEWS);
  const [open, setOpen] = useState<Media | null>(null);
  const [stage, setStage] = useState<Stage>("after");
  const [region, setRegion] = useState<string>(PHOTO_REGIONS[0]);
  const [photoView, setPhotoView] = useState<string>(PHOTO_VIEWS[0]);
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const photos = (data ?? []).filter((m) => view === ALL_VIEWS || m.view === view);

  function choosePhoto(chosen: File | null) {
    const message = chosen === null ? null : checkPhotoFile(chosen);
    setProblem(message ?? "");
    setFile(message === null ? chosen : null);
    if (message !== null && fileInput.current !== null) fileInput.current.value = "";
  }

  async function recordConsent() {
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.POST("/api/v1/patients/{patient_id}/consents", {
          params: { path: { patient_id: patientId } },
          body: { kind: "media", granted: true, source: "Ghi nhận ở tab Ảnh" },
        }),
      );
      toast.push("success", "Đã ghi nhận đồng ý sử dụng hình ảnh.");
      onChanged();
    } catch (e) {
      setProblem(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (file === null) {
      setProblem("Hãy chọn một ảnh.");
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await uploadPhoto({ patientId, file, stage, region, view: photoView });
      toast.push("success", "Đã tải ảnh lên.");
      setFile(null);
      if (fileInput.current !== null) fileInput.current.value = "";
      reload();
      onChanged();
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card
        title="Ảnh trước / sau"
        subtitle="Lưu và xem ảnh lâm sàng của người bệnh. Hệ thống không phân tích nội dung ảnh."
        aside={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={consentGranted ? "success" : "warning"}>
              {consentGranted ? "Đã đồng ý ảnh" : "Chưa có đồng ý ảnh"}
            </Badge>
            {!consentGranted && canRecordConsent && (
              <Button variant="secondary" disabled={busy} onClick={() => void recordConsent()}>
                Ghi nhận đồng ý
              </Button>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-0">
            <label
              htmlFor="photo-view-filter"
              className="mb-1.5 block text-label font-semibold text-ink-soft"
            >
              Góc ảnh
            </label>
            <select
              id="photo-view-filter"
              value={view}
              onChange={(e) => setView(e.target.value)}
              className={`${FIELD_CONTROL_CLASS} sm:w-52`}
            >
              <option value={ALL_VIEWS}>Tất cả các góc</option>
              {PHOTO_VIEWS.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </div>
        </div>
        {error !== "" && (
          <div className="mt-3">
            <RetryNotice message={error} onRetry={reload} />
          </div>
        )}
        {loading && data === undefined && <ListSkeleton rows={2} />}
        {!consentGranted && (
          <div className="mt-3">
            <Notice tone="warn">
              Người bệnh chưa có đồng ý sử dụng hình ảnh: không thể tải ảnh mới lên, và nhân viên
              chăm sóc không xem được ảnh đã có.
            </Notice>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {STAGES.map((s) => {
          const ofStage = photos.filter((m) => m.stage === s);
          return (
            <Card key={s} title={MEDIA_STAGE_LABEL[s]} subtitle={`${ofStage.length} ảnh`}>
              {data !== undefined && ofStage.length === 0 && (
                <Muted>Chưa có ảnh ở giai đoạn này.</Muted>
              )}
              <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-2 xl:grid-cols-3">
                {ofStage.map((m) => (
                  <PhotoTile key={m.id} media={m} onOpen={() => setOpen(m)} />
                ))}
              </ul>
            </Card>
          );
        })}
      </div>

      {canUpload && (
        <Card
          title="Thêm ảnh"
          subtitle="Cần đồng ý hình ảnh của người bệnh. PNG, JPEG hoặc WebP, tối đa 8 MB."
        >
          <form onSubmit={(e) => void submit(e)} noValidate>
            <TwoCol>
              <Field label="Giai đoạn">
                {(control) => (
                  <select
                    {...control}
                    value={stage}
                    onChange={(e) => setStage(e.target.value === "before" ? "before" : "after")}
                    className={FIELD_CONTROL_CLASS}
                  >
                    {STAGES.map((s) => (
                      <option key={s} value={s}>
                        {MEDIA_STAGE_LABEL[s]}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
              <Field label="Tệp ảnh">
                {(control) => (
                  <input
                    {...control}
                    ref={fileInput}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={(e) => choosePhoto(e.target.files?.[0] ?? null)}
                    className={`${FIELD_CONTROL_CLASS} file:mr-3 file:rounded-control file:border-0 file:bg-tile file:px-3 file:py-1.5`}
                  />
                )}
              </Field>
            </TwoCol>
            <TwoCol>
              <Field label="Vùng chụp">
                {(control) => (
                  <select
                    {...control}
                    value={region}
                    onChange={(e) => setRegion(e.target.value)}
                    className={FIELD_CONTROL_CLASS}
                  >
                    {PHOTO_REGIONS.map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                )}
              </Field>
              <Field label="Góc chụp">
                {(control) => (
                  <select
                    {...control}
                    value={photoView}
                    onChange={(e) => setPhotoView(e.target.value)}
                    className={FIELD_CONTROL_CLASS}
                  >
                    {PHOTO_VIEWS.map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                )}
              </Field>
            </TwoCol>
            <Button type="submit" disabled={busy || !consentGranted}>
              Tải ảnh lên
            </Button>
            <FormError message={problem} />
          </form>
        </Card>
      )}

      {open !== null && (
        <Dialog
          title={MEDIA_STAGE_LABEL[open.stage]}
          subtitle={captionOf(open)}
          onClose={() => setOpen(null)}
          wide
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={open.content_path}
            alt={altOf(open)}
            className="mx-auto max-h-[70dvh] w-auto max-w-full object-contain"
          />
        </Dialog>
      )}
    </div>
  );
}
