// Tags of a knowledge-base source that make it an article of the staff guide (`/guide`): the tag `guide` plus one
// topic (the old `role` eyebrow). The backend keeps at most 10 tags of 1 to 40 characters.
export const GUIDE_TAG = "guide";
export const MAX_TOPIC_LENGTH = 40;

export type GuideTagsDraft = { guide: boolean; topic: string };

/** The draft a source starts from: `guide` ticked when the tag is there, the first other tag as the topic. */
export function draftOfTags(tags: readonly string[]): GuideTagsDraft {
  return { guide: tags.includes(GUIDE_TAG), topic: tags.find((tag) => tag !== GUIDE_TAG) ?? "" };
}

/** The tags to save: `[guide, topic]` when ticked (no empty topic), nothing otherwise (the article is hidden). */
export function tagsOfDraft(draft: GuideTagsDraft): string[] {
  const topic = draft.topic.trim().slice(0, MAX_TOPIC_LENGTH);
  if (!draft.guide) return [];
  return topic === "" ? [GUIDE_TAG] : [GUIDE_TAG, topic];
}
