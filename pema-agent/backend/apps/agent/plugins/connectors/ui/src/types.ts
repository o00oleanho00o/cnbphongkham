/** What the plugin's admin routes send and take (`/v1/plugins/connectors`); mirrors `routes.py`. */

export interface ConnectorChannel {
  name: string;
  /** ISO time the connector last spoke for the channel. */
  seen_at: string | null;
  markdown: boolean;
  max_text_chars: number | null;
  /** The channel hub has started the channel (it takes messages). */
  listening: boolean;
}

export interface Connector {
  name: string;
  created_at: string | null;
  revoked: boolean;
  revoked_at: string | null;
  channels: ConnectorChannel[];
}

export interface Created {
  name: string;
  /** Shown once; the agent keeps it sealed and never gives it back. */
  key: string;
}
