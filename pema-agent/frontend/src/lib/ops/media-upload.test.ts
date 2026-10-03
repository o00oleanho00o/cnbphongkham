import { describe, expect, it } from "vitest";

import type { Schemas } from "@/lib/api";

import {
  PHOTO_EMPTY_MESSAGE,
  PHOTO_MAX_BYTES,
  PHOTO_SIZE_MESSAGE,
  PHOTO_TYPE_MESSAGE,
  checkPhotoFile,
  uploadPhoto,
  type UploadApi,
} from "./media-upload";

type Media = Schemas["MediaOut"];

const MEDIA: Media = {
  id: "m-1",
  patient_id: "p-1",
  session_id: null,
  stage: "after",
  region: null,
  view: null,
  mime: "image/jpeg",
  size_bytes: 3,
  status: "confirmed",
  consent_id: "c-1",
  consent_active: true,
  created_at: "2026-09-20T09:00:00+07:00",
  content_path: "/api/v1/media/m-1/content",
  version: 3,
};

/** Hand-written fake of the three calls; it records what the flow asked for, in order. */
function fakeApi(): { api: UploadApi; calls: string[] } {
  const calls: string[] = [];
  const api: UploadApi = {
    intent: (_patientId, body) => {
      calls.push(`intent ${body.mime} ${body.size_bytes} ${body.stage}`);
      return Promise.resolve({
        media_id: "m-1",
        upload_path: "/api/v1/media/m-1/content?exp=1&sig=s",
        method: "PUT",
        mime: body.mime,
        max_bytes: PHOTO_MAX_BYTES,
        expires_at: "2026-09-20T09:10:00+07:00",
      });
    },
    put: (path) => {
      calls.push(`put ${path}`);
      return Promise.resolve({ ...MEDIA, status: "uploaded" });
    },
    confirm: (mediaId) => {
      calls.push(`confirm ${mediaId}`);
      return Promise.resolve(MEDIA);
    },
  };
  return { api, calls };
}

const jpeg = (size = 3): File =>
  new File([new Uint8Array(size)], "anh.jpg", { type: "image/jpeg" });

describe("checkPhotoFile", () => {
  it("a_jpeg_png_or_webp_within_the_ceiling_is_accepted", () => {
    expect(
      ["image/jpeg", "image/png", "image/webp"].map((type) => checkPhotoFile({ type, size: 10 })),
    ).toEqual([null, null, null]);
  });

  it("a_gif_is_refused_with_the_type_sentence", () => {
    expect(checkPhotoFile({ type: "image/gif", size: 10 })).toBe(PHOTO_TYPE_MESSAGE);
  });

  it("a_file_above_eight_megabytes_is_refused", () => {
    expect(checkPhotoFile({ type: "image/png", size: PHOTO_MAX_BYTES + 1 })).toBe(
      PHOTO_SIZE_MESSAGE,
    );
  });

  it("an_empty_file_is_refused", () => {
    expect(checkPhotoFile({ type: "image/png", size: 0 })).toBe(PHOTO_EMPTY_MESSAGE);
  });
});

describe("uploadPhoto", () => {
  it("asks_for_the_path_sends_the_bytes_there_and_confirms_in_that_order", async () => {
    const { api, calls } = fakeApi();

    const media = await uploadPhoto({ patientId: "p-1", file: jpeg(), stage: "before" }, api);

    expect(calls).toEqual([
      "intent image/jpeg 3 before",
      "put /api/v1/media/m-1/content?exp=1&sig=s",
      "confirm m-1",
    ]);
    expect(media.status).toBe("confirmed");
  });

  it("a_file_the_browser_can_already_see_is_wrong_never_reaches_the_server", async () => {
    const { api, calls } = fakeApi();
    const gif = new File([new Uint8Array(3)], "a.gif", { type: "image/gif" });

    await expect(uploadPhoto({ patientId: "p-1", file: gif, stage: "after" }, api)).rejects.toThrow(
      PHOTO_TYPE_MESSAGE,
    );
    expect(calls).toEqual([]);
  });
});
