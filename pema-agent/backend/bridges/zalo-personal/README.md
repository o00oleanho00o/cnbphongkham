# zalo-personal bridge

A small Node 22+ sidecar (Hono) around [`zca-js`](https://github.com/RFS-ADRENO/zca-js) 2.1.2 that lets the Pema
backend use a **personal Zalo account** as a messaging channel. `zca-js` is not ported to Python: it stays here, behind
a flag, and the Python side talks to it over signed HTTP (`pema/channels/zalo_personal/bridge_client.py`). It is the
Node half of the faithful port of `vuhai2002/zalo-agent` (`src/zalo/zalo-client.ts`, `zalo-listener.ts`,
`reconnect-planner.ts`, `qr-login-manager.ts`, `reaction-icons.ts`).

## WARNING: risk of account lock and breach of the Zalo terms

**`zca-js` is an unofficial, reverse-engineered client of the Zalo web app.** Using it:

- **can get the Zalo account locked or permanently banned** by Zalo, without notice and without appeal;
- **may breach the Zalo terms of service**. The clinic's owner, not the developers, accepts that risk;
- is not the official API (the official channels are the Zalo Bot API and, later, the OA/ZNS APIs).

Rules that follow from this, and that the code enforces where it can:

1. Use a **SECONDARY account only**: never the clinic's main account, never an account whose loss would hurt (a
   number patients already know, an account tied to payments or to the owner's personal life).
2. Zalo allows ONE web listener per account. Opening Zalo Web on the same account kicks the bridge's listener, and the
   bridge reconnecting kicks the web session back. Do not keep Zalo Web open on this account.
3. Keep volume low and human-like. The bridge adds hard per-account ceilings on top of the daily cap and the random gaps
   of the API (see "Safety design").
4. Never put real patient data in test conversations of this account while evaluating.

## Safety design

| Layer             | What it does                                                                                                                                                                                                                                                                                                               |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Flag              | `PEMA_ZALO_PERSONAL_ENABLED` is `false` in code. When false every route except `GET /health` answers `503 bridge_disabled` and `zca-js` is never instantiated. `.env.example` sets it to `true`, but **nothing runs until somebody scans a QR code** (or the API pushes a stored credential).                              |
| Secondary account | See the warning above. The admin UI creates personal accounts with the `patient_channel` policy profile by default (every outgoing text is reviewed by a person).                                                                                                                                                          |
| Daily cap         | The API caps proactive messages per (account, thread, day) with `SCHEDULER_MAX_PROACTIVE_PER_DAY` (default 10, configurable per channel in the admin UI). The bridge adds its own ceiling, `ZALO_BRIDGE_MAX_PROACTIVE_PER_DAY_PER_ACCOUNT` (default 100), and `ZALO_BRIDGE_MAX_SENDS_PER_MINUTE_PER_ACCOUNT` (default 20). |
| Kill switch       | Instant. Off by default. Set from the admin UI, from the API, or straight on the bridge (`pnpm kill-switch on`). Scope `proactive` blocks every proactive message, scope `all` blocks every send.                                                                                                                          |
| Breaker           | After `ZALO_BRIDGE_BLOCK_AFTER_REJECTED_SENDS` (default 5) consecutive sends refused by the Zalo server the account goes `blocked`, refuses all sends and the bridge reports `account_state: blocked`.                                                                                                                     |
| Credential        | The Zalo cookie, `imei` and user agent are **never written to disk** by the bridge. The API stores them encrypted (AES-256-GCM, `PEMA_SECRET_ENCRYPTION_KEY`) in `agent.accounts.credential_enc` and hands them over in the body of the signed `start` request; the bridge keeps them in memory.                           |
| Transport         | The bridge listens on loopback by default. Every request, and every event it posts, carries an HMAC-SHA256 signature (`PEMA_ZALO_BRIDGE_SECRET`) with a 5 minute replay window.                                                                                                                                            |
| Logs              | No message text, name, phone number, cookie, credential, QR image or secret is ever logged.                                                                                                                                                                                                                                |

## What happens when Zalo locks or logs the account out

The bridge posts an `account_state` event (`blocked`, `logged_out` or `session_dead`). The API then: stores the bridge
state on the channel (`clinic.channel_setting.bridge_state`), **turns the kill switch on** (reason `bridge_blocked`,
`bridge_logged_out` or `bridge_session_dead`), drops the channel from its registry and writes an audit row. From that
moment every proactive send is rejected with `channel_kill_switch_on`, which is the signal that moves the scheduled
messages of the account to **manual sending** by staff. A reconnect never turns the kill switch off by itself: a person
decides when sending resumes. After a `logged_out` or `session_dead` the account needs a new QR scan.

## How to scan the QR code

1. In the admin UI open **Channels** and enable the Zalo personal channel (flag `enabled`). Create the account in
   **Accounts** (channel `zalo_personal`, a secondary account).
2. Open the account and press **Login**. The API calls `POST /v1/accounts/:id/login/qr` on the bridge and the UI polls
   the state. The QR code is valid for about 3 minutes; when it expires the bridge produces a new one.
3. On the phone open Zalo, **Scan QR** (the QR icon of the search bar), scan the code shown on the screen.
4. The state moves `waiting_scan` -> `scanned` (the phone asks you to confirm) -> `success`. Confirm on the phone.
   `declined` means you refused on the phone; start again.
5. On `success` the bridge posts `credential_updated` (the API stores it encrypted) and starts the listener. Later
   restarts use the stored credential: no new scan is needed unless Zalo logs the account out.

The QR image is the key to the account: it only travels through the authenticated admin API and is never logged.

## EMERGENCY OFF

Fastest first. Any one of them stops the sending.

1. **Admin UI**: Channels > Zalo personal > **Kill switch** (stops proactive sends in every process at once, and tells
   the bridge). To stop replies too, switch the channel flag `enabled` off: every account is stopped.
2. **From a terminal on the bridge host**, without the API or the UI:

   ```sh
   pnpm kill-switch on --scope all --reason "emergency"   # blocks every send of every account
   pnpm kill-switch status
   pnpm kill-switch off
   ```

   It reads `PEMA_ZALO_BRIDGE_SECRET`, `PEMA_ZALO_BRIDGE_HOST` and `PEMA_ZALO_BRIDGE_PORT` from the environment or `.env`
   and signs the request the same way the API does.

3. **Stop every account** (listeners closed, credentials dropped from the bridge's memory): a signed
   `POST /v1/accounts/stop-all`.
4. **Disable the bridge**: set `PEMA_ZALO_PERSONAL_ENABLED=false` and restart it.
5. **Kill the process**.
6. Last resort, on the phone: Zalo > Settings > Account and security > **logged-in devices** > log the web session out.

## Protocol

All routes are under `/v1`, JSON, signed in both directions.

**Auth.** Headers `X-Pema-Timestamp` (unix seconds) and `X-Pema-Signature` = lowercase hex
`HMAC-SHA256(secret, "<timestamp>.<raw body bytes>")` (a request without a body signs the empty string). A bad
signature, a body that does not match, or `|now - timestamp| > 300 s` answers `401 unauthorized`. `GET /health` is the
only unsigned route and returns `{ok, enabled, accounts}`.

**Answers.** Success `{ok: true, ...}`. Failure `{ok: false, error: {kind, message, code?}}` with `kind` one of
`zalo_rejected` (a `ZaloApiError`: `code` is its numeric code, HTTP 502), `transport` (502), `bridge_disabled` (503),
`kill_switch` (409), `rate_limited` (429), `blocked` (409), `not_running` (409), `bad_request` (400/422),
`unauthorized` (401). The Python side retries without styles/quote only for `zalo_rejected` (the Zalo server answered
and nothing was delivered).

**Routes (API to bridge).**

- `POST /accounts/:id/start` `{credential:{cookie, imei, userAgent}, kill_switch?:{on, scope, reason?}}` -> `{own_id}`
- `POST /accounts/:id/stop`, `POST /accounts/stop-all`, `GET /accounts`, `GET /accounts/:id/state`
- `POST /accounts/:id/login/qr` `{}`, `GET /accounts/:id/login/qr` -> `{state, qr_png_base64?, error?}`
- `POST /accounts/:id/send` `{thread_id, thread_type: 0|1, text, styles?, quote?, mentions?, proactive}` -> `{msg_id}`.
  Gates, in order: running, kill switch, breaker, per-minute ceiling, per-day proactive ceiling.
- `POST /accounts/:id/typing`, `/receipts/delivered`, `/receipts/seen`, `/reaction`
- `GET /accounts/:id/user-info?uid=`, `GET /accounts/:id/friends` (only `userId`, `displayName`, `zaloName`),
  `POST /accounts/:id/friends/accept|reject`, `GET /accounts/:id/group-info?thread_id=`
- `POST /accounts/:id/send-attachment`, `POST /accounts/:id/send-video` (same gates as `send`)
- `POST /kill-switch` `{on, scope?, reason?}`, `GET /kill-switch`

**Events (bridge to API)**, posted to `{PEMA_API_BASE_URL}/webhooks/zalo-bridge/{account_id}`, signed,
retried 3 times with backoff: `message`, `friend_event` (`kind`: `add|remove|request|undo_request|reject_request|other`),
`credential_updated`, `account_state` (`connected|disconnected|session_dead|logged_out|blocked`).

## Configuration

See `.env.example`. Hard backstops: `ZALO_BRIDGE_MAX_PROACTIVE_PER_DAY_PER_ACCOUNT`,
`ZALO_BRIDGE_MAX_SENDS_PER_MINUTE_PER_ACCOUNT`, `ZALO_BRIDGE_BLOCK_AFTER_REJECTED_SENDS`.

## Development

```sh
pnpm install
pnpm test           # node --test with tsx; no network, a fake zca-js gateway
pnpm typecheck
pnpm lint
pnpm format:check
```

The tests never log in to Zalo. Everything in them is synthetic.

## License

This bridge is a derivative of `vuhai2002/zalo-agent` and depends on `zca-js` (both MIT); their notices are in
[`../../../THIRD_PARTY_NOTICES.md`](../../../THIRD_PARTY_NOTICES.md).
