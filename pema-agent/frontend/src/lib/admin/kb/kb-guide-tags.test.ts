import { describe, expect, it } from "vitest";

import { draftOfTags, MAX_TOPIC_LENGTH, tagsOfDraft } from "./kb-guide-tags";

describe("draftOfTags", () => {
  it("reads_the_guide_tick_and_the_first_other_tag_as_topic", () => {
    expect(draftOfTags(["guide", "CSKH"])).toEqual({ guide: true, topic: "CSKH" });
  });

  it("is_not_a_guide_article_without_the_tag", () => {
    expect(draftOfTags([])).toEqual({ guide: false, topic: "" });
  });
});

describe("tagsOfDraft", () => {
  it("saves_the_tag_and_the_trimmed_topic", () => {
    expect(tagsOfDraft({ guide: true, topic: "  Lễ tân " })).toEqual(["guide", "Lễ tân"]);
  });

  it("saves_only_the_tag_when_the_topic_is_empty", () => {
    expect(tagsOfDraft({ guide: true, topic: "   " })).toEqual(["guide"]);
  });

  it("saves_nothing_when_the_article_is_hidden", () => {
    expect(tagsOfDraft({ guide: false, topic: "CSKH" })).toEqual([]);
  });

  it("cuts_a_long_topic_to_the_length_the_backend_accepts", () => {
    const topic = tagsOfDraft({ guide: true, topic: "a".repeat(80) })[1] ?? "";
    expect(topic).toHaveLength(MAX_TOPIC_LENGTH);
  });
});
