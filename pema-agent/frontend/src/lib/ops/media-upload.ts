// Upload of a clinical photo (package U, step U3): ask the BE for a signed path, send the bytes there, confirm.
// Nothing here opens, resizes or analyses the image: the browser only hands the file over (PLAN-AI01-U
// principle 6). The BE repeats the type, size and consent checks; checking the file here only saves a round trip.
import type { Schemas } from "@/lib/api";
import { ApiError, http, unwrap } from "@/lib/api/client";

export const PHOTO_MAX_BYTES = 8 * 1024 * 1024;
export const PHOTO_MIME_TYPES: readonly string[] = ["image/jpeg", "image/png", "image/webp"];

export const PHOTO_TYPE_MESSAGE = "Chỉ nhận ảnh PNG, JPEG hoặc WebP.";
export const PHOTO_SIZE_MESSAGE = "Ảnh vượt quá 8 MB.";
export const PHOTO_EMPTY_MESSAGE = "Tệp ảnh trống.";

type Media = Schemas["MediaOut"];
type Target = Schemas["MediaUploadTarget"];

/** What the browser knows about a chosen file (a `File` has both). */
export type PhotoFile = { type: string; size: number };

/** The first problem of a chosen file, or null. Same rules, same words as the BE. */
export function checkPhotoFile(file: PhotoFile): string | null {
  if (!PHOTO_MIME_TYPES.includes(file.type)) return PHOTO_TYPE_MESSAGE;
  if (file.size <= 0) return PHOTO_EMPTY_MESSAGE;
  if (file.size > PHOTO_MAX_BYTES) return PHOTO_SIZE_MESSAGE;
  return null;
}

export type PhotoUpload = {
  patientId: string;
  file: File;
  stage: Schemas["MediaStage"];
  sessionId?: string | null;
  region?: string | null;
  view?: string | null;
};

/** The three calls of the flow, so a test can run it without a network. */
export type UploadApi = {
  intent: (patientId: string, body: Schemas["MediaUploadIntent"]) => Promise<Target>;
  put: (path: string, file: File) => Promise<Media>;
  confirm: (mediaId: string) => Promise<Media>;
};

async function errorFrom(response: Response): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as {
    error?: { message?: string; code?: Schemas["ErrorCode"] };
  } | null;
  return new ApiError(
    response.status,
    body?.error?.message ?? `Lỗi ${response.status}`,
    body?.error?.code,
  );
}

export const httpUploadApi: UploadApi = {
  intent: (patientId, body) =>
    unwrap(
      http.POST("/api/v1/patients/{patient_id}/media/upload-intent", {
        params: { path: { patient_id: patientId } },
        body,
      }),
    ),
  put: async (path, file) => {
    // The signed path is relative to the API origin and already carries its expiry and signature.
    const response = await fetch(path, {
      method: "PUT",
      body: file,
      headers: { "content-type": file.type },
      credentials: "include",
    }).catch(() => {
      throw new ApiError(0, "Không kết nối được server");
    });
    if (!response.ok) throw await errorFrom(response);
    return (await response.json()) as Media;
  },
  confirm: (mediaId) =>
    unwrap(
      http.POST("/api/v1/media/{media_id}/confirm", { params: { path: { media_id: mediaId } } }),
    ),
};

/** Intent, bytes, confirm. Throws `ApiError` (the BE's sentence) or an `Error` with the file problem. */
export async function uploadPhoto(
  input: PhotoUpload,
  api: UploadApi = httpUploadApi,
): Promise<Media> {
  const problem = checkPhotoFile(input.file);
  if (problem !== null) throw new Error(problem);
  const target = await api.intent(input.patientId, {
    stage: input.stage,
    mime: input.file.type,
    size_bytes: input.file.size,
    session_id: input.sessionId ?? null,
    region: input.region ?? null,
    view: input.view ?? null,
  });
  await api.put(target.upload_path, input.file);
  return api.confirm(target.media_id);
}
