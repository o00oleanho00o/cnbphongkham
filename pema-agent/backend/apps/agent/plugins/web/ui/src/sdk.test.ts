import { describe, expect, it } from "vitest";

import { contributions, forget, register } from "./sdk";

describe("the plugin registry", () => {
  it("keeps the last contribution of each plugin and forgets one switched off", () => {
    const page = () => null;
    const before = contributions();
    register("zalo", { pages: [{ id: "accounts", title: "Zalo", component: page }] });
    register("zalo", { pages: [{ id: "friends", title: "Bạn bè", component: page }] });
    register("other", {});
    forget("other");
    forget("missing");

    const after = contributions();
    expect([...after.keys()]).toEqual(["zalo"]);
    expect(after.get("zalo")?.pages?.map((p) => p.id)).toEqual(["friends"]);
    expect(after).not.toBe(before);
  });
});
