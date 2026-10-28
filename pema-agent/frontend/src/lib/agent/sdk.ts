// The plugin SDK host (plan C): the clinic web plays the agent dashboard's part (`plugins/web/ui/src/sdk.ts`) so the
// pages a plugin ships run here. A plugin's script is an IIFE with React left outside (`window.__PEMA_AGENT__.React`
// and `.jsxRuntime`), so it renders with this app's React; it calls `window.__PEMA_AGENT__.register(name,
// {pages})`. Its calls go through `api` (same-origin `/agent/...`, the proxy signs them) and it draws with `ui`.
import * as React from "react";
import type { ComponentType } from "react";
import { useSyncExternalStore } from "react";
import * as jsxRuntime from "react/jsx-runtime";

import { type Kit, pluginKit } from "@/components/agent/plugin-kit";

import {
  AGENT_PREFIX,
  type Api,
  agentApi,
  CONNECTORS_PREFIX,
  connectorApi,
  createAgentApi,
} from "./api";

export interface PluginPage {
  /** Part of the address: `/admin/agent/plugins/<plugin>/<id>`. */
  id: string;
  title: string;
  component: ComponentType;
}

export interface Contribution {
  pages?: PluginPage[];
  /** A top-level tab of its own for this plugin's area (the knowledge store), opening the page `page`. The clinic
   * web adds it to "Điều khiển agent" while the plugin is enabled; the agent dashboard lists the pages as usual. */
  section?: { title: string; page: string };
  /** Display names of the people of a channel (chat lists), `{ <user id>: <name> }` for the ones it knows; a plugin
   * answers `{}` for a channel that is not its own. */
  personNames?: (channel: string, userIds: readonly string[]) => Promise<Record<string, string>>;
  /** Set by the host, never by a script: the connector whose script registered this (its pages are the connector's
   * own, not an agent plugin's: no agent plugin page, no switch). */
  connector?: string;
}

export interface Sdk {
  version: 1;
  React: typeof React;
  jsxRuntime: typeof jsxRuntime;
  api: Api;
  /** Only in a connector's script: the agent's own `api`, for the agent routes its pages show beside its own (the
   * tools an account may switch off, the skills bound to a channel). Same session, same permissions. */
  agentApi?: Api;
  ui: Kit;
  register(plugin: string, contribution: Contribution): void;
}

declare global {
  interface Window {
    __PEMA_AGENT__?: Sdk;
  }
}

export type Registered = ReadonlyMap<string, Contribution>;

const NOTHING: Registered = new Map();
const listeners = new Set<() => void>();
let registered: Registered = NOTHING;
/** Plugin name -> the script loaded for it. */
const loaded = new Map<string, string>();
let running: Promise<string[]> | null = null;

function changed(next: Registered): void {
  registered = next;
  listeners.forEach((listener) => listener());
}

export function register(plugin: string, contribution: Contribution): void {
  changed(new Map(registered).set(plugin, contribution));
}

/** Drops a plugin's pages and the note that its script ran (it runs again when the plugin comes back). */
export function forget(plugin: string): void {
  loaded.delete(plugin);
  if (!registered.has(plugin)) return;
  const next = new Map(registered);
  next.delete(plugin);
  changed(next);
}

export function contributions(): Registered {
  return registered;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useContributions(): Registered {
  return useSyncExternalStore(subscribe, contributions, () => NOTHING);
}

export function installAgentSdk(api: Api = agentApi): void {
  window.__PEMA_AGENT__ = { version: 1, React, jsxRuntime, api, ui: pluginKit, register };
}

interface UiListing {
  plugins: { name: string; script: string; styles: string[] }[];
}

function addScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(src));
    document.head.append(script);
  });
}

function addStyle(href: string): void {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.append(link);
}

interface ConnectorUi {
  name: string;
  script: string;
  styles: string[];
}

/** Connector name -> the script loaded for it. */
const loadedConnectors = new Map<string, string>();

/** The SDK a connector's script sees: the same host, but its `api` goes to `/connectors/<name>` and what it registers
 * is marked with the connector. A script keeps the `sdk` it found when it ran, so its pages keep this `api`. */
function sdkFor(base: Sdk, connector: string): Sdk {
  return {
    ...base,
    api: connectorApi(connector),
    agentApi: base.api,
    register: (plugin, contribution) => register(plugin, { ...contribution, connector }),
  };
}

function forgetConnector(name: string): void {
  loadedConnectors.delete(name);
  [...registered]
    .filter(([, contribution]) => contribution.connector === name)
    .forEach(([plugin]) => forget(plugin));
}

/** Loads one connector's script; a connector that is down or answers an error just shows no pages. True when it ran. */
async function loadConnector(base: Sdk, name: string): Promise<boolean> {
  const prefix = `${CONNECTORS_PREFIX}/${name}`;
  try {
    const ui = await connectorApi(name).get<ConnectorUi>("/v1/admin/ui");
    if (loadedConnectors.get(name) === ui.script) return true;
    (ui.styles ?? []).forEach((href) => addStyle(`${prefix}${href}`));
    window.__PEMA_AGENT__ = sdkFor(base, name);
    try {
      await addScript(`${prefix}${ui.script}`);
    } finally {
      window.__PEMA_AGENT__ = base;
    }
    loadedConnectors.set(name, ui.script);
    return true;
  } catch {
    forgetConnector(name);
    return false;
  }
}

/** One after the other: a script reads `window.__PEMA_AGENT__` while it runs, so only one may be loading at a time. */
async function loadConnectors(): Promise<string[]> {
  const base = window.__PEMA_AGENT__;
  const listing = await createAgentApi({ prefix: CONNECTORS_PREFIX })
    .get<{ connectors: string[] }>("")
    .catch(() => ({ connectors: [] as string[] }));
  const names = listing.connectors.filter((name) => /^[a-z0-9_-]+$/.test(name));
  [...loadedConnectors.keys()].filter((name) => !names.includes(name)).forEach(forgetConnector);
  if (!base) return [];
  return names.reduce<Promise<string[]>>(
    async (failed, name) => [...(await failed), ...((await loadConnector(base, name)) ? [] : [name])],
    Promise.resolve([]),
  );
}

async function load(api: Api): Promise<string[]> {
  const listing = await api.get<UiListing>("/v1/admin/ui");
  const enabled = new Set(listing.plugins.map((p) => p.name));
  [...new Set([...registered.keys(), ...loaded.keys()])]
    .filter((name) => !enabled.has(name) && registered.get(name)?.connector === undefined)
    .forEach(forget);
  const fresh = listing.plugins.filter((plugin) => loaded.get(plugin.name) !== plugin.script);
  const outcomes = await Promise.all(
    fresh.map(async (plugin) => {
      plugin.styles.forEach((href) => addStyle(`${AGENT_PREFIX}${href}`));
      try {
        await addScript(`${AGENT_PREFIX}${plugin.script}`);
        loaded.set(plugin.name, plugin.script);
        return null;
      } catch {
        return plugin.name;
      }
    }),
  );
  // After the agent's scripts have all run, so none of them can see a connector's SDK.
  const connectorsFailed = await loadConnectors();
  return [...outcomes.filter((name): name is string => name !== null), ...connectorsFailed];
}

/**
 * Adds the scripts and styles of the enabled plugins not loaded yet and forgets the plugins switched off. Resolves
 * to the names of the plugins whose script failed; rejects (`ApiError`) when the list itself cannot be read.
 * Calls made while one runs share it.
 */
export function loadPlugins(api: Api = agentApi): Promise<string[]> {
  running ??= load(api).finally(() => {
    running = null;
  });
  return running;
}
