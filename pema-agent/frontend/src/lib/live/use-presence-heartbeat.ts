"use client";

// Tell the backend "I am looking at / answering this conversation" every PRESENCE_INTERVAL_MS while it is
// open (and straight away when the state changes), so colleagues see "Lan đang xem / đang trả lời". It is a
// warning, never a lock: a failed beat is ignored and never blocks the person from replying. Nothing is sent
// while the tab is hidden; coming back sends one beat at once. Closing the conversation sends a leave call
// (best effort); when that is lost the backend lets the last beat expire after 30 seconds.
import { useEffect } from "react";

import { leavePresence, postPresence } from "@/lib/live/live-api";
import type { PresenceState } from "@/lib/live/live-types";

export const PRESENCE_INTERVAL_MS = 15_000;

export function usePresenceHeartbeat(conversationId: string, state: PresenceState): void {
  useEffect(() => {
    const beat = () => {
      if (document.visibilityState === "hidden") return;
      postPresence(conversationId, state).catch(() => undefined);
    };
    beat();
    const timer = setInterval(beat, PRESENCE_INTERVAL_MS);
    document.addEventListener("visibilitychange", beat);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", beat);
    };
  }, [conversationId, state]);

  // Keyed by the conversation only: a change from viewing to replying must not look like leaving.
  useEffect(
    () => () => {
      leavePresence(conversationId).catch(() => undefined);
    },
    [conversationId],
  );
}
