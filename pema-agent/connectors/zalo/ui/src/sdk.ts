/** The host's SDK: the clinic web sets `window.__PEMA_AGENT__` up before it loads this script. Its `api` here talks to
 * this connector (the host puts `/connectors/zalo` in front of every path); the types below are the contract of the
 * host (frontend/src/lib/agent/sdk.ts and components/agent/plugin-kit.tsx), kept here so this folder builds alone. */
import type {
  ButtonHTMLAttributes,
  ComponentType,
  InputHTMLAttributes,
  ReactElement,
  ReactNode,
  SelectHTMLAttributes,
} from "react";

export type KitTone = "neutral" | "info" | "success" | "warning" | "danger";

export interface Api {
  get<T>(path: string): Promise<T>;
  post<T>(path: string, body?: unknown): Promise<T>;
  put<T>(path: string, body?: unknown): Promise<T>;
  patch<T>(path: string, body?: unknown): Promise<T>;
  del<T>(path: string): Promise<T>;
}

export interface Kit {
  Button: (
    props: ButtonHTMLAttributes<HTMLButtonElement> & {
      variant?: "primary" | "secondary" | "danger" | "ghost";
      busy?: boolean;
    },
  ) => ReactElement;
  Card: (props: { title?: ReactNode; aside?: ReactNode; children: ReactNode }) => ReactElement;
  PageHeader: (props: { title: string; subtitle?: string; aside?: ReactNode }) => ReactElement;
  Field: (props: { label: string; hint?: ReactNode; error?: string; children: ReactNode }) => ReactElement;
  Input: (props: InputHTMLAttributes<HTMLInputElement>) => ReactElement;
  Select: (
    props: SelectHTMLAttributes<HTMLSelectElement> & { options: readonly { value: string; label: string }[] },
  ) => ReactElement;
  Toggle: (props: {
    checked: boolean;
    onChange: (next: boolean) => void;
    label: string;
    disabled?: boolean;
  }) => ReactElement;
  Badge: (props: { tone?: KitTone; children: ReactNode }) => ReactElement;
  Notice: (props: { tone?: KitTone; children: ReactNode }) => ReactElement;
  Empty: (props: { children: ReactNode }) => ReactElement;
  FIELD_CLASS: string;
}

export interface Contribution {
  pages?: { id: string; title: string; component: ComponentType }[];
  /** Display names of the people of a channel, `{ <user id>: <name> }`; `{}` for a channel that is not ours. */
  personNames?: (channel: string, userIds: readonly string[]) => Promise<Record<string, string>>;
}

export interface Sdk {
  version: 1;
  api: Api;
  /** The agent's own `api` (skills, plugin list), next to this connector's `api`. */
  agentApi?: Api;
  ui: Kit;
  register(plugin: string, contribution: Contribution): void;
}

declare global {
  interface Window {
    __PEMA_AGENT__?: Sdk;
  }
}

const found = window.__PEMA_AGENT__;
if (!found) throw new Error("The Zalo pages run inside the Pema clinic web (Điều khiển agent)");

export const sdk: Sdk = found;
export const { api, ui } = found;
export const agentApi: Api = found.agentApi ?? found.api;
