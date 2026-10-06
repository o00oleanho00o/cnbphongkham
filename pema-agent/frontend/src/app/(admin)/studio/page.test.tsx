// @vitest-environment jsdom
// The before/after studio (`/studio`): choose a patient, then the view and the comparison mode, with the notices
// the old web showed (alignment not checked, nothing medical to read from illustrative images, consent on record or
// not). The server rules (who may open, the consent) are the backend's
// (`backend/apps/api/tests/clinic/test_catalog_resources.py`).
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Schemas } from "@/lib/api";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import StudioRoute from "./page";

// The typed HTTP client is the boundary to an unmanaged dependency (the backend API), so it is replaced by a
// fake whose answers each test sets; the screen's own logic runs for real. The address bar is replaced too: its
// search string is what the screen reads and writes.
const api = vi.hoisted(() => ({ get: vi.fn() }));
const nav = vi.hoisted(() => ({ search: "", replace: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { GET: (...args: unknown[]) => api.get(...args) } };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const PATIENT_ID = "patient-1";
const PATIENTS: Schemas["Page_PatientOut_"] = {
  items: [{ id: PATIENT_ID, code: "P001", full_name: "Nguyễn Thu Hà" } as Schemas["PatientOut"]],
  total: 1,
  limit: 8,
  offset: 0,
};

function studio(overrides: Partial<Schemas["StudioOut"]> = {}): Schemas["StudioOut"] {
  return {
    patient_id: PATIENT_ID,
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    concern: "Nám · tăng sắc tố",
    view: "Chính diện",
    views: ["Chính diện", "Má trái", "Má phải"],
    media_consent: true,
    photos: [],
    ...overrides,
  };
}

function ok<T>(data: T) {
  return Promise.resolve({ data, response: new Response(null, { status: 200 }) });
}

function renderPage(permissions: Permission[] = ["patient.read", "patient.read_360"]) {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "c-1",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "BS. Lê Minh Tâm",
        role: "doctor",
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <StudioRoute />
    </SessionProvider>,
  );
}

beforeEach(() => {
  nav.search = "";
  nav.replace.mockReset();
  api.get.mockReset().mockImplementation((path: string) => {
    if (path === "/api/v1/patients") return ok(PATIENTS);
    return ok(studio());
  });
});

afterEach(() => cleanup());

describe("choosing the patient", () => {
  it("lists_patients_and_puts_the_choice_in_the_address", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Nguyễn Thu Hà/ }));

    expect(nav.replace).toHaveBeenCalledWith("/studio?patient=patient-1");
  });

  it("refuses_a_role_without_access_to_photos", () => {
    renderPage(["patient.read"]);

    expect(screen.getByText("Bạn không có quyền xem ảnh bệnh nhân")).toBeTruthy();
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe("comparing", () => {
  beforeEach(() => {
    nav.search = `patient=${PATIENT_ID}`;
  });

  it("shows_the_patient_the_placeholders_and_the_notices_of_the_old_web", async () => {
    renderPage();

    expect(await screen.findByText("Before / After Studio")).toBeTruthy();
    expect(screen.getByText("Nguyễn Thu Hà · P001 · Nám · tăng sắc tố")).toBeTruthy();
    expect(screen.getByText("MINH HỌA TRƯỚC")).toBeTruthy();
    expect(screen.getByText("MINH HỌA SAU")).toBeTruthy();
    expect(screen.getByText(/Chưa có ảnh upload ở góc này/)).toBeTruthy();
    expect(
      screen.getByText(/Chưa kiểm định căn chỉnh ảnh; bác sĩ kiểm tra điều kiện chụp/),
    ).toBeTruthy();
    expect(screen.getByText(/Không suy ra hiệu quả y khoa từ ảnh minh họa/)).toBeTruthy();
    expect(
      screen.getByText(
        /Metadata: vùng Mặt; góc Chính diện; mốc buổi minh họa; đồng ý chăm sóc: có ghi nhận/,
      ),
    ).toBeTruthy();
  });

  it("asks_the_backend_for_the_view_picked", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Before / After Studio");

    await user.selectOptions(screen.getByLabelText("Góc ảnh so sánh"), "Má trái");

    expect(nav.replace).toHaveBeenCalledWith("/studio?patient=patient-1&view=M%C3%A1+tr%C3%A1i");
  });

  it("loads_the_view_in_the_address", async () => {
    nav.search = `patient=${PATIENT_ID}&view=${encodeURIComponent("Má phải")}`;
    renderPage();

    await waitFor(() => {
      const call = api.get.mock.calls.find((c) => c[0] === "/api/v1/studio/{patient_id}");
      const options = call?.[1] as { params: { query: { view: string } } };
      expect(options.params.query.view).toBe("Má phải");
    });
  });

  it("switches_between_side_by_side_and_the_slider", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "So sánh trượt" }));

    expect(screen.getByLabelText("Vị trí đường so sánh")).toBeTruthy();
    expect(screen.getByText("Trước ← → Sau")).toBeTruthy();
    expect(screen.queryByText("MINH HỌA TRƯỚC")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Đặt cạnh nhau" }));

    expect(screen.getByText("MINH HỌA TRƯỚC")).toBeTruthy();
  });

  it("warns_when_no_media_consent_is_on_record", async () => {
    api.get.mockImplementation(() => ok(studio({ media_consent: false })));
    renderPage();

    expect(await screen.findByText(/Chưa có đồng ý sử dụng ảnh/)).toBeTruthy();
    expect(screen.getByText(/đồng ý chăm sóc: chưa xác nhận/)).toBeTruthy();
  });

  it("sends_add_photo_to_the_patients_record_where_the_consent_is_taken", async () => {
    renderPage();

    const link = await screen.findByRole("link", { name: /Thêm ảnh/ });

    expect(link.getAttribute("href")).toBe("/patients/patient-1");
  });
});
