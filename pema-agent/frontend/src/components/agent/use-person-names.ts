"use client";

// The display names of the people of a list of chats, asked from the plugins that know them (a plugin registers
// `personNames` with the SDK): one call per channel and plugin for a whole page of rows, never one per row. A plugin
// that fails or knows nobody leaves the person unnamed; the list shows the user id then.
import { useEffect, useState } from "react";

import { peopleByChannel, personKey, type SessionRow } from "@/lib/agent/activity";
import { useContributions } from "@/lib/agent/sdk";

export function usePersonNames(
  rows: readonly Pick<SessionRow, "channel" | "user_id">[],
): Map<string, string> {
  const registered = useContributions();
  const [names, setNames] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    let stale = false;
    const resolvers = [...registered.values()].flatMap((c) =>
      c.personNames ? [c.personNames] : [],
    );
    if (resolvers.length === 0) return;
    const asks = [...peopleByChannel(rows)].flatMap(([channel, users]) =>
      resolvers.map((resolve) =>
        resolve(channel, users).then(
          (found) =>
            Object.entries(found).map(([user, name]) => [personKey(channel, user), name] as const),
          () => [],
        ),
      ),
    );
    void Promise.all(asks).then((answers) => {
      if (!stale) setNames(new Map(answers.flat()));
    });
    return () => {
      stale = true;
    };
  }, [rows, registered]);

  return names;
}
