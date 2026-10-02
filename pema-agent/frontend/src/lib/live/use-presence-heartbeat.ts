"use client";

// Tell the backend "I am looking at / answering this conversation" every PRESENCE_INTERVAL_MS while it is
// open (and straight away when the state changes), so colleagues see "Lan đang xem / đang trả lời". It is a
// warning, never a lock: a failed beat is ignored and never blocks the person from replying. Nothing is sent
// while the tab is hidden; coming back sends one beat at once. No leave call: the backend lets a beat expire.
import { useEffect } from "react";

import { postPresence } from "@/lib/live/live-api";
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
}
