/**
 * Outbound routes: send, typing, receipts, reaction.
 *
 * New module (no TS original); the calls themselves are the original's (`duongGuiZcaJs`,
 * `sendTypingEvent`, `sendDeliveredEvent`/`sendSeenEvent`, `addReaction`).
 *
 * Every send passes the safety gates BEFORE zca-js is called, in this order: not running, kill switch,
 * breaker (blocked), per-minute ceiling, per-day proactive ceiling. Only `send` is a send; typing,
 * receipts and reactions are not gated by the ceilings.
 */
import { Hono } from "hono";
import type { AccountManager, ManagedAccount } from "./account-registry.js";
import type { AppDeps } from "./deps.js";
import { fail, failFromThrown, ok, parseJsonBody, type AppEnv } from "./http.js";
import { createLogger, errorInfo } from "./logger.js";
import { toZaloReaction } from "./reaction-icons.js";
import {
  accountIdSchema,
  deliveredBodySchema,
  reactionBodySchema,
  seenBodySchema,
  sendBodySchema,
  toZcaQuote,
  toZcaStyles,
  typingBodySchema,
} from "./schemas.js";
import type { KillSwitch } from "./safety.js";
import { duongGuiZcaJs, laLoiMayChuTuChoi } from "./zalo-send.js";
import type { ZaloApi } from "./zalo-types.js";

const log = createLogger("routes-messaging");

type MsgId = number | bigint | string;
/** `sendMessage` answers `{message, attachment[]}`. */
type SendOutcome = { message?: { msgId: MsgId } | null } | null | undefined;

/** zca-js ids are numbers that can exceed 2^53, so the wire carries them as strings. */
function messageIdOf(result: unknown): string | null {
  // zca-js' answer shape, read-only here; anything else yields no id.
  const outcome = result as SendOutcome;
  const id = outcome?.message?.msgId;
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
      duongGuiZcaJs(
        api,
        thread_id,
        thread_type,
      )({
        text,
        ...(styles ? { styles } : {}),
        ...(quote ? { quote } : {}),
        ...(mentions ? { mentions } : {}),
      }),
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
