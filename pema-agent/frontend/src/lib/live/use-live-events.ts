"use client";

// `useLiveEvents`: subscribe a screen to `GET /api/v1/events`. The screen says which event types it cares
// about and what to do (usually "reload my list quietly"); connection, reconnection, the 10 second rule and
// the 30 second polling fallback live in LiveConnection. Listener and timers are released on unmount.
import { useEffect, useRef, useState } from "react";

import { LiveConnection, type EventSourceLike, type LiveMode } from "@/lib/live/live-connection";
import type { LiveEvent, LiveEventType } from "@/lib/live/live-types";

type UseLiveEventsOptions = {
  /** Event types this screen reacts to. Pass a module-level constant (a new array restarts the stream). */
  types: readonly LiveEventType[];
  onEvent: (event: LiveEvent) => void;
  /** The stream came back after a gap, or the polling fallback ticked: reload what you show. */
  onRefresh: () => void;
  /** Test seam: replaces `new EventSource(url)`. */
  createSource?: (url: string) => EventSourceLike;
};

/** `"live"` while events flow, `"polling"` when the stream has been down for over 10 seconds. */
export function useLiveEvents({
  types,
  onEvent,
  onRefresh,
  createSource,
}: UseLiveEventsOptions): LiveMode {
  const [mode, setMode] = useState<LiveMode>("connecting");
  // The latest callbacks, so the connection is not torn down when a screen re-renders.
  const eventRef = useRef(onEvent);
  const refreshRef = useRef(onRefresh);
  useEffect(() => {
    eventRef.current = onEvent;
    refreshRef.current = onRefresh;
  });

  useEffect(() => {
    const connection = new LiveConnection({
      types,
      createSource,
      onEvent: (event) => eventRef.current(event),
      onRefresh: () => refreshRef.current(),
      onMode: setMode,
    });
    connection.start();
    return () => connection.close();
  }, [types, createSource]);

  return mode;
}
