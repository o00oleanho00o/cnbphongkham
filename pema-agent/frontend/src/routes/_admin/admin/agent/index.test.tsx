// @vitest-environment jsdom
// `/admin/agent`: opens the agent overview.
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const router = vi.hoisted(() => ({ replace: vi.fn() }));

// next/navigation needs the Next runtime: the router is the browser API the page talks to.
vi.mock("@/lib/navigation", () => ({ useRouter: () => router }));

import { componentOf } from "@/lib/route-component";

import { Route } from "./index";

const AgentIndex = componentOf(Route);

beforeEach(() => router.replace.mockReset());

afterEach(cleanup);

describe("the agent index", () => {
  it("opens_the_overview", () => {
    render(<AgentIndex />);

    expect(router.replace).toHaveBeenCalledWith("/admin/agent/overview");
  });
});
