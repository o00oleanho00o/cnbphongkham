// Words for "who else is on this conversation". Pure, so the sentence is tested without a screen.
// Colleagues are called by their given name (the last word in Vietnamese), keeping a "BS." title in front.
import type { PresenceState, PresenceViewer } from "@/lib/live/live-types";

const MAX_NAMES = 2;
const TITLE_PREFIX = /^(BS\.?|ThS\.?|TS\.?)\s+/i;

const STATE_PHRASE: Record<PresenceState, string> = {
  replying: "đang trả lời",
  viewing: "đang xem",
};

// Replying first: that is the one a second person must not step on.
const STATE_ORDER: readonly PresenceState[] = ["replying", "viewing"];

export function shortName(fullName: string): string {
  const name = fullName.trim().replace(/\s+/g, " ");
  const title = TITLE_PREFIX.exec(name)?.[0].trim();
  const rest = title ? name.slice(title.length).trim() : name;
  const given = rest.split(" ").at(-1) ?? "";
  if (!given) return title ?? "Một đồng nghiệp";
  return title ? `${title} ${given}` : given;
}

function phraseFor(state: PresenceState, viewers: readonly PresenceViewer[]): string | null {
  const names = viewers.filter((v) => v.state === state).map((v) => shortName(v.name));
  if (names.length === 0) return null;
  const shown = names.slice(0, MAX_NAMES).join(", ");
  const more = names.length > MAX_NAMES ? ` và ${names.length - MAX_NAMES} người khác` : "";
  return `${shown}${more} ${STATE_PHRASE[state]}`;
}

/** "Lan đang trả lời · Hà đang xem", or null when nobody else is on the conversation. */
export function presenceText(viewers: readonly PresenceViewer[]): string | null {
  const phrases = STATE_ORDER.map((state) => phraseFor(state, viewers)).filter(
    (phrase): phrase is string => phrase !== null,
  );
  return phrases.length === 0 ? null : phrases.join(" · ");
}

/** True when somebody else is writing a reply: the warning shown beside the reply box. */
export function someoneReplying(viewers: readonly PresenceViewer[]): boolean {
  return viewers.some((v) => v.state === "replying");
}

/** The state to report: a started draft means "replying", an open conversation means "viewing". */
export function presenceStateFor(draft: string): PresenceState {
  return draft.trim().length > 0 ? "replying" : "viewing";
}
