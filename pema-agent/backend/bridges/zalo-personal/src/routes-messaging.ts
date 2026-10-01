/**
 * Outbound routes: send, send-attachment, send-video, typing, receipts, reaction.
 *
 * New module (no TS original); the calls themselves are the original's (`duongGuiZcaJs`,
 * `sendTypingEvent`, `sendDeliveredEvent`/`sendSeenEvent`, `addReaction`, `sendVideo`).
 *
 * Every send passes the safety gates BEFORE zca-js is called, in this order: not running, kill switch,
 * breaker (blocked), per-minute ceiling, per-day proactive ceiling. Only `send`, `send-attachment` and
 * `send-video` are sends; typing, receipts and reactions are not gated by the ceilings.
 */
import { Hono } from "hono";
import type { AccountManager, ManagedAccount } from "./account-registry.js";
import type { AppDeps } from "./deps.js";
import {
  fail,
  failFromThrown,
  ok,
  parseJsonBody,
  type AppEnv,
} from "./http.js";
import { createLogger, errorInfo } from "./logger.js";
import { toZaloReaction } from "./reaction-icons.js";
import {
  MAX_ATTACHMENT_BYTES,
  accountIdSchema,
  deliveredBodySchema,
  reactionBodySchema,
  seenBodySchema,
  sendAttachmentBodySchema,
  sendBodySchema,
  sendVideoBodySchema,
  toZcaQuote,
  toZcaStyles,
  typingBodySchema,
} from "./schemas.js";
import type { KillSwitch } from "./safety.js";
import { checkPublicHttpUrl } from "./url-guard.js";
import { buildAttachmentSource, duongGuiZcaJs, laLoiMayChuTuChoi } from "./zalo-send.js";
import type { ZaloApi } from "./zalo-types.js";

const log = createLogger("routes-messaging");

type MsgId = number | bigint | string;
/** `sendMessage` answers `{message, attachment[]}`, `sendVideo` answers `{msgId}`. */
type SendOutcome =
  | { msgId?: MsgId; message?: { msgId: MsgId } | null; attachment?: Array<{ msgId: MsgId }> }
  | null
  | undefined;

/** zca-js ids are numbers that can exceed 2^53, so the wire carries them as strings. */
function messageIdOf(result: unknown): string | null {
  // zca-js' two answer shapes, both read-only here; anything else yields no id.
  const outcome = result as SendOutcome;
  const id = outcome?.msgId ?? outcome?.message?.msgId ?? outcome?.attachment?.[0]?.msgId;
  return id === undefined ? null : String(id);
}

type Gates = { accounts: AccountManager; killSwitch: KillSwitch };

/**
 * Run one send behind the safety gates. `run` is the only place that talks to zca-js.
 * The breaker counts CONSECUTIVE `zalo_rejected` failures; a success resets it.
 */
async function guardedSend(
  gates: Gates,
  accountId: string,
  proactive: boolean,
  run: (api: ZaloApi) => Promise<unknown>,
): Promise<Response> {
  const account = gates.accounts.get(accountId);
  const api = account?.canSend ? account.api : null;
  if (!account || !api) return fail("not_running", "Account is not running");

  const kill = gates.killSwitch.get();
  if (gates.killSwitch.blocks(proactive)) {
    return fail("kill_switch", `Kill switch is on (scope ${kill.scope})`);
  }

  const admission = account.safety.admit(proactive);
  if (!admission.ok) return fail(admission.kind, admission.message);

  try {
    const result = await run(api);
    account.safety.succeeded();
    return ok({ msg_id: messageIdOf(result) });
  } catch (err) {
    const outcome = account.safety.failed(admission.reservation, laLoiMayChuTuChoi(err));
    log.warn({ accountId, proactive, ...errorInfo(err) }, "Send failed");
    if (outcome.blockedNow) {
      log.error({ accountId }, "Account blocked after repeated rejected sends");
      gates.accounts.reportBlocked(account);
    }
    return failFromThrown(err);
  }
}

/** Decode base64 and enforce the 10 MB cap on the DECODED size (checked before allocating). */
function decodeAttachment(base64: string): Buffer | null {
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(base64)) return null;
  const padding = base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0;
  const decodedSize = Math.floor((base64.length * 3) / 4) - padding;
  if (decodedSize > MAX_ATTACHMENT_BYTES) return null;
  return Buffer.from(base64, "base64");
}

export function messagingRoutes(deps: AppDeps): Hono<AppEnv> {
  const { accounts, killSwitch } = deps;
  const gates: Gates = { accounts, killSwitch };
  const app = new Hono<AppEnv>();

  const idOf = (raw: string | undefined): string | null => {
    const parsed = accountIdSchema.safeParse(raw);
    return parsed.success ? parsed.data : null;
  };
  const badId = (): Response => fail("bad_request", "invalid account id");

  /** The running account's api for a call that is not a gated send. */
  const apiFor = (id: string): ZaloApi | null => {
    const account: ManagedAccount | undefined = accounts.get(id);
    return account?.canSend ? account.api : null;
  };
  const notRunning = (): Response => fail("not_running", "Account is not running");

  app.post("/accounts/:id/send", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    const body = parseJsonBody(c, sendBodySchema);
    if (!body.ok) return body.response;
    const { thread_id, thread_type, text, proactive, mentions } = body.data;
    const styles = toZcaStyles(body.data.styles);
    const quote = toZcaQuote(body.data.quote);

    // Styles and mentions only when non-empty, quote only when present: `duongGuiZcaJs` applies the rules.
    return guardedSend(gates, id, proactive, (api) =>
      duongGuiZcaJs(api, thread_id, thread_type)({
        text,
        ...(styles ? { styles } : {}),
        ...(quote ? { quote } : {}),
        ...(mentions ? { mentions } : {}),
      }),
    );
  });

  app.post("/accounts/:id/send-attachment", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    const body = parseJsonBody(c, sendAttachmentBodySchema);
    if (!body.ok) return body.response;
    const { thread_id, thread_type, filename, data_base64, caption, proactive } = body.data;

    const data = decodeAttachment(data_base64);
    if (!data) return fail("bad_request", "data_base64 is not valid base64 or exceeds 10 MB");
    // The regex of the schema guarantees "<name>.<ext>"; the template type cannot express it.
    const source = buildAttachmentSource(filename as `${string}.${string}`, data);

    return guardedSend(gates, id, proactive, (api) =>
      api.sendMessage({ msg: caption, attachments: [source] }, thread_id, thread_type),
    );
  });

  app.post("/accounts/:id/send-video", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    const body = parseJsonBody(c, sendVideoBodySchema);
    if (!body.ok) return body.response;
    const { thread_id, thread_type, video_url, caption, proactive } = body.data;

    const verdict = await checkPublicHttpUrl(video_url, deps.lookupHost);
    if (!verdict.ok) return fail("bad_request", verdict.message);
    if (body.data.thumbnail_url !== undefined) {
      const thumb = await checkPublicHttpUrl(body.data.thumbnail_url, deps.lookupHost);
      if (!thumb.ok) return fail("bad_request", "thumbnail_url host is not public");
    }

    return guardedSend(gates, id, proactive, (api) =>
      api.sendVideo(
        {
          msg: caption,
          videoUrl: video_url,
          thumbnailUrl: body.data.thumbnail_url ?? "",
          ...(body.data.duration_ms === undefined ? {} : { duration: body.data.duration_ms }),
          ...(body.data.width === undefined ? {} : { width: body.data.width }),
          ...(body.data.height === undefined ? {} : { height: body.data.height }),
        },
        thread_id,
        thread_type,
      ),
    );
  });

  app.post("/accounts/:id/typing", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    const body = parseJsonBody(c, typingBodySchema);
    if (!body.ok) return body.response;
    const api = apiFor(id);
    if (!api) return notRunning();
    try {
      await api.sendTypingEvent(body.data.thread_id, body.data.thread_type);
      return ok();
    } catch (err) {
      return failFromThrown(err);
    }
  });

  app.post("/accounts/:id/receipts/delivered", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    const body = parseJsonBody(c, deliveredBodySchema);
    if (!body.ok) return body.response;
    const api = apiFor(id);
    if (!api) return notRunning();
    try {
      // isSeen = false: this is "đã nhận"; "đã xem" goes through /receipts/seen.
      await api.sendDeliveredEvent(body.data.is_seen, body.data.params, body.data.thread_type);
      return ok();
    } catch (err) {
      return failFromThrown(err);
    }
  });

  app.post("/accounts/:id/receipts/seen", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    const body = parseJsonBody(c, seenBodySchema);
    if (!body.ok) return body.response;
    const api = apiFor(id);
    if (!api) return notRunning();
    try {
      await api.sendSeenEvent(body.data.params, body.data.thread_type);
      return ok();
    } catch (err) {
      return failFromThrown(err);
    }
  });

  app.post("/accounts/:id/reaction", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    const body = parseJsonBody(c, reactionBodySchema);
    if (!body.ok) return body.response;
    const api = apiFor(id);
    if (!api) return notRunning();
    try {
      await api.addReaction(toZaloReaction(body.data.icon_key), {
        data: { msgId: body.data.msg_id, cliMsgId: body.data.cli_msg_id },
        threadId: body.data.thread_id,
        type: body.data.thread_type,
      });
      return ok();
    } catch (err) {
      return failFromThrown(err);
    }
  });

  return app;
}
