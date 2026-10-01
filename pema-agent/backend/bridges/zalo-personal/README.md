# zalo-personal bridge

Placeholder owned by package C2: a small Node 22 sidecar (Hono) around `zca-js` 2.1.2 for the
personal-account Zalo channel. zca-js is NOT ported to Python (PORT-MAP, dependency mapping).

Constraints the implementation must keep:

* off by default (`PEMA_ZALO_PERSONAL_ENABLED=false`); a secondary account only;
* behind `ChannelPort`: the Python side is `pema/channels/zalo_personal/bridge_client.py`;
* inbound events go to `POST /api/v1/webhooks/zalo-bridge/{clinic_slug}/{account_id}` with an HMAC
  (`PEMA_ZALO_BRIDGE_SECRET`); outbound send, QR login and friends are API -> bridge over HTTP;
* daily proactive cap (default 10 per conversation, `SCHEDULER_MAX_PROACTIVE_PER_DAY`), random gap, send
  window and the kill switch (`/admin/channels/{channel}/kill-switch`) are enforced;
* the Zalo credential is stored encrypted in `agent.accounts.credential_enc` (`secret_cipher`), never in a file;
* the README of the finished bridge must state the RISK OF ACCOUNT LOCK: zca-js is an unofficial,
  reverse-engineered client and opening Zalo Web on the same account kicks the listener.
