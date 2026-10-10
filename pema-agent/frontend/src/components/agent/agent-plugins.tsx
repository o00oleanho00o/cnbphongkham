"use client";

// The agent plugins of the section `/admin/agent`: the layout installs the SDK and loads the enabled plugins' scripts
// once; the plugin pages read the outcome here and the registered pages from the SDK's store.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { Notice, RetryNotice, Spinner } from "@/components/ops/ops-ui";
import { ApiError, type Api, agentApi } from "@/lib/agent/api";
import { pluginHref } from "@/lib/agent/plugins";
import { installAgentSdk, loadPlugins, useContributions, type Registered } from "@/lib/agent/sdk";

export type PluginsState =
  | { kind: "loading" }
  | { kind: "ready"; failed: readonly string[] }
  | { kind: "error"; status: number; message: string };

type PluginsValue = {
  state: PluginsState;
  retry: () => void;
  registered: Registered;
};

const PluginsContext = createContext<PluginsValue | null>(null);

/** Where a page a plugin ships is drawn: below the plugin's own page. */
export function pluginPageHref(plugin: string, page: string): string {
  return `${pluginHref(plugin)}/${encodeURIComponent(page)}`;
}

/** A failed call to the agent as the state `PluginsProblem` draws (401, 403 with the API's sentence, the rest). */
export function failure(err: unknown): Extract<PluginsState, { kind: "error" }> {
  if (err instanceof ApiError) return { kind: "error", status: err.status, message: err.message };
  return {
    kind: "error",
    status: 0,
    message: err instanceof Error ? err.message : "Có lỗi xảy ra",
  };
}

export function AgentPluginsProvider({
  api = agentApi,
  children,
}: {
  api?: Api;
  children: ReactNode;
}) {
  const [state, setState] = useState<PluginsState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const registered = useContributions();

  useEffect(() => {
    let stale = false;
    installAgentSdk(api);
    loadPlugins(api).then(
      (failed) => {
        if (!stale) setState({ kind: "ready", failed });
      },
      (err: unknown) => {
        if (!stale) setState(failure(err));
      },
    );
    return () => {
      stale = true;
    };
  }, [api, attempt]);

  const retry = useCallback(() => {
    setState({ kind: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  const value = useMemo<PluginsValue>(
    () => ({ state, retry, registered }),
    [state, retry, registered],
  );
  return <PluginsContext.Provider value={value}>{children}</PluginsContext.Provider>;
}

export function useAgentPlugins(): PluginsValue {
  const value = useContext(PluginsContext);
  if (!value) throw new Error("useAgentPlugins must be used inside AgentPluginsProvider");
  return value;
}

/** What to show while the plugins load or when they could not be loaded. */
export function PluginsProblem({
  state,
  retry,
}: {
  state: Exclude<PluginsState, { kind: "ready" }>;
  retry: () => void;
}) {
  if (state.kind === "loading") return <Spinner label="Đang tải trang plugin" />;
  if (state.status === 401) {
    return <Notice>Phiên đăng nhập đã hết. Đang chuyển tới trang đăng nhập…</Notice>;
  }
  if (state.status === 403) return <Notice tone="warn">{state.message}</Notice>;
  return <RetryNotice message={`Không tải được trang plugin: ${state.message}`} onRetry={retry} />;
}
