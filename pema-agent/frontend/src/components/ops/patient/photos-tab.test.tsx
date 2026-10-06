// @vitest-environment jsdom
// The Ảnh trước / sau tab: photos in a grid by stage, the consent they rest on, and no upload without it.
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PhotosTab } from "@/components/ops/patient/photos-tab";
import { PATIENT_ID, asRole, ok, photo } from "@/components/ops/patient/test-support";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
    },
  };
});

const PHOTOS = [
  photo({ id: "m1", stage: "before", content_path: "/api/v1/media/m1/content" }),
  photo({ id: "m2", stage: "after", content_path: "/api/v1/media/m2/content" }),
  photo({ id: "m3", stage: "after", view: "Má trái", content_path: "/api/v1/media/m3/content" }),
];

function renderTab(options: { consent: boolean; upload?: boolean; recordConsent?: boolean }) {
  return render(
    asRole(
      ["media.read"],
      <PhotosTab
        patientId={PATIENT_ID}
        consentGranted={options.consent}
        canUpload={options.upload ?? true}
        canRecordConsent={options.recordConsent ?? true}
        onChanged={() => undefined}
      />,
    ),
  );
}

const sourcesIn = (heading: string): (string | null)[] => {
  const section = screen.getByRole("heading", { name: heading }).closest("section");
  return within(section as HTMLElement)
    .getAllByRole("img")
    .map((img) => img.getAttribute("src"));
};

beforeEach(() => {
  api.get.mockReset().mockResolvedValue(ok(PHOTOS));
  api.post.mockReset().mockResolvedValue(ok({}));
});

afterEach(() => cleanup());

describe("PhotosTab", () => {
  it("puts_each_photo_in_the_column_of_its_stage_and_streams_it_from_the_backend", async () => {
    renderTab({ consent: true });
    await screen.findByRole("heading", { name: "Trước điều trị" });

    expect(sourcesIn("Trước điều trị")).toEqual(["/api/v1/media/m1/content"]);
    expect(sourcesIn("Sau điều trị")).toEqual([
      "/api/v1/media/m2/content",
      "/api/v1/media/m3/content",
    ]);
  });

  it("the_angle_filter_keeps_only_that_angle", async () => {
    renderTab({ consent: true });
    await screen.findByRole("heading", { name: "Trước điều trị" });

    await userEvent.setup().selectOptions(screen.getByLabelText("Góc ảnh"), "Má trái");

    expect(sourcesIn("Sau điều trị")).toEqual(["/api/v1/media/m3/content"]);
  });

  it("with_the_consent_it_says_so_and_allows_the_upload", async () => {
    renderTab({ consent: true });

    expect(await screen.findByText("Đã đồng ý ảnh")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tải ảnh lên" }).hasAttribute("disabled")).toBe(
      false,
    );
  });

  it("without_the_consent_it_warns_and_the_upload_button_is_disabled", async () => {
    renderTab({ consent: false });

    expect(await screen.findByText("Chưa có đồng ý ảnh")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tải ảnh lên" }).hasAttribute("disabled")).toBe(true);
  });

  it("someone_who_may_record_consent_can_do_it_from_here", async () => {
    renderTab({ consent: false });

    await userEvent.setup().click(await screen.findByRole("button", { name: "Ghi nhận đồng ý" }));

    const sent = (api.post.mock.calls[0]?.[1] as { body: { kind: string; granted: boolean } }).body;
    expect([sent.kind, sent.granted]).toEqual(["media", true]);
  });

  it("someone_who_cannot_upload_has_no_upload_form", async () => {
    renderTab({ consent: true, upload: false });
    await screen.findByRole("heading", { name: "Trước điều trị" });

    expect(screen.queryByRole("button", { name: "Tải ảnh lên" })).toBeNull();
  });
});
