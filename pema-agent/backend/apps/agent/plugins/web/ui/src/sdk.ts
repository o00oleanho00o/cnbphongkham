/**
 * How other plugins add pages to the dashboard (their browser half). A plugin ships one script, built as an IIFE
 * with React left outside (`react` -> `window.__PEMA_AGENT__.React`, `react/jsx-runtime` ->
 * `window.__PEMA_AGENT__.jsxRuntime`), and declares it in its manifest (`[ui] entry`). Once signed in, the
 * dashboard asks `GET /v1/admin/ui` which plugins are enabled and loads their scripts; each calls
 * `window.__PEMA_AGENT__.register(name, {pages})`. Pages use `sdk.api` (signed calls) and `sdk.ui` (the kit).
 * Classes come from the dashboard's stylesheet, which scans the bundled plugins' sources; an installed plugin
 * ships its own CSS (`[ui] styles`).
 */
import * as React from "react";
import type { ComponentType } from "react";
import * as jsxRuntime from "react/jsx-runtime";
import { useSyncExternalStore } from "react";

import { type Api, api } from "./lib/api";
import { type Kit, ui } from "./ui/kit";

export interface PluginPage {
  /** Part of the address: `#/p/<plugin>/<id>`. */
  id: string;
  title: string;
  component: ComponentType;
}

export interface Contribution {
  pages?: PluginPage[];
}

export interface Sdk {
  version: 1;
  React: typeof React;
  jsxRuntime: typeof jsxRuntime;
  api: Api;
  ui: Kit;
  register(plugin: string, contribution: Contribution): void;
}

declare global {
  interface Window {
    __PEMA_AGENT__?: Sdk;
  }
}

type Registered = ReadonlyMap<string, Contribution>;

const listeners = new Set<() => void>();
let registered: Registered = new Map();

export function register(plugin: string, contribution: Contribution): void {
  const next = new Map(registered);
  next.set(plugin, contribution);
  registered = next;
  listeners.forEach((listener) => listener());
}

export function forget(plugin: string): void {
  if (!registered.has(plugin)) return;
  const next = new Map(registered);
  next.delete(plugin);
  registered = next;
  listeners.forEach((listener) => listener());
}

export function contributions(): Registered {
  return registered;
}

export function useContributions(): Registered {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, contributions);
}

export function installSdk(): void {
  window.__PEMA_AGENT__ = { version: 1, React, jsxRuntime, api, ui, register };
}

interface UiListing {
  plugins: { name: string; script: string; styles: string[] }[];
}

const loaded = new Map<string, string>();

/** Adds the scripts and styles of enabled plugins not loaded yet; pages of plugins switched off go away. */
export async function loadPlugins(): Promise<string[]> {
  const listing = await api.get<UiListing>("/v1/admin/ui");
  const enabled = new Set(listing.plugins.map((p) => p.name));
  for (const name of new Set([...registered.keys(), ...loaded.keys()])) {
    if (enabled.has(name)) continue;
    forget(name);
    loaded.delete(name);
  }
  const failed: string[] = [];
  for (const plugin of listing.plugins) {
    if (loaded.get(plugin.name) === plugin.script) continue;
    plugin.styles.forEach((href) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      document.head.append(link);
    });
    try {
      await addScript(plugin.script);
      loaded.set(plugin.name, plugin.script);
    } catch {
      failed.push(plugin.name);
    }
  }
  return failed;
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
