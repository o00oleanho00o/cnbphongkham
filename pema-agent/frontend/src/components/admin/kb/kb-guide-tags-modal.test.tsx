// @vitest-environment jsdom
// The dialog that puts a knowledge-base source into the staff guide: it starts from the tags the source has, sends
// `[guide, topic]` (or nothing when the tick is off) and shows the backend's sentence when the save fails.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KbGuideTagsModal } from "./kb-guide-tags-modal";

const api = vi.hoisted(() => ({ put: vi.fn() }));

// The HTTP client is the unmanaged dependency: a hand-written fake of the one route the dialog calls.
vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { PUT: (...args: unknown[]) => api.put(...args) } };
});

const saved = { id: "kb-1", title: "Quy trình", topic: "CSKH", tags: ["guide", "CSKH"] };
const ok = () => Promise.resolve({ data: saved, response: new Response(null, { status: 200 }) });

type Handlers = { closed: number; savedCount: number };

function renderModal(tags: readonly string[], handlers: Handlers = { closed: 0, savedCount: 0 }) {
  render(
    <KbGuideTagsModal
      sourceId="kb-1"
      sourceName="Quy trình tiếp đón"
      tags={tags}
      onClose={() => {
        handlers.closed += 1;
      }}
      onSaved={() => {
        handlers.savedCount += 1;
      }}
    />,
  );
  return handlers;
}

const sentTags = (): unknown =>
  (api.put.mock.calls.at(-1)?.[1] as { body: { tags: unknown } } | undefined)?.body.tags;

beforeEach(() => {
  api.put.mockReset().mockImplementation(ok);
});

afterEach(cleanup);

describe("guide tags dialog", () => {
  it("starts_from_the_tags_the_source_has", () => {
    renderModal(["guide", "Lễ tân"]);
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/Chủ đề hoặc vai trò/) as HTMLInputElement).value).toBe("Lễ tân");
  });

  it("puts_a_plain_source_into_the_guide_with_a_topic", async () => {
    const handlers = renderModal([]);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.type(screen.getByLabelText(/Chủ đề hoặc vai trò/), " CSKH ");
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(handlers.savedCount).toBe(1));
    expect(sentTags()).toEqual(["guide", "CSKH"]);
    expect(handlers.closed).toBe(1);
  });

  it("takes_an_article_out_of_the_guide_by_sending_no_tags", async () => {
    renderModal(["guide", "CSKH"]);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(sentTags()).toEqual([]);
  });

  it("the_topic_box_is_off_while_the_source_is_not_in_the_guide", () => {
    renderModal([]);
    expect((screen.getByLabelText(/Chủ đề hoặc vai trò/) as HTMLInputElement).disabled).toBe(true);
  });

  it("shows_why_a_save_failed_and_stays_open", async () => {
    api.put.mockReset().mockImplementation(() => Promise.reject(new Error("offline")));
    const handlers = renderModal(["guide"]);
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(handlers.closed).toBe(0);
  });
});
