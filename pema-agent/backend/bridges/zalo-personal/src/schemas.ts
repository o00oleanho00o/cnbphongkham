/**
 * zod schemas of the request bodies of the wire protocol (see README, "Protocol").
 *
 * New module (no TS original). `proactive` is REQUIRED on every send: the Python side must say whether a
 * message is proactive (it counts toward the daily ceiling and is blocked by a `proactive` kill switch),
 * a missing flag must never silently mean "not proactive".
 */
import { TextStyle } from "zca-js";
import type { SendMessageQuote, Style } from "zca-js";
import { z } from "zod";

export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

export const accountIdSchema = z.string().regex(/^[A-Za-z0-9._:-]{1,128}$/, "invalid account id");
export const clinicSlugSchema = z.string().regex(/^[A-Za-z0-9_-]{1,64}$/, "invalid clinic_slug");

const threadIdSchema = z.string().min(1).max(64);
const threadTypeSchema = z.union([z.literal(0), z.literal(1)]);
const idLikeSchema = z.union([z.string().min(1), z.number()]).transform(String);

const cookieSchema = z.union([
  z.array(z.record(z.string(), z.unknown())).min(1),
  z.object({ url: z.string(), cookies: z.array(z.record(z.string(), z.unknown())).min(1) }),
]);

export const credentialSchema = z.object({
  cookie: cookieSchema,
  imei: z.string().min(1),
  userAgent: z.string().min(1),
});

export const killSwitchSchema = z.object({
  on: z.boolean(),
  scope: z.enum(["proactive", "all"]).optional(),
  reason: z.string().max(500).optional(),
});

export const startBodySchema = z.object({
  clinic_slug: clinicSlugSchema,
  credential: credentialSchema,
  kill_switch: killSwitchSchema.optional(),
});

export const qrBodySchema = z.object({ clinic_slug: clinicSlugSchema });

const styleSchema = z.object({
  start: z.number().int().min(0),
  len: z.number().int().min(1),
  st: z.enum(TextStyle),
  indentSize: z.number().int().min(0).optional(),
});

const quoteSchema = z.object({
  content: z.union([z.string(), z.record(z.string(), z.unknown())]),
  msgType: z.string(),
  propertyExt: z.record(z.string(), z.unknown()).optional(),
  uidFrom: z.string(),
  msgId: idLikeSchema,
  cliMsgId: idLikeSchema,
  ts: idLikeSchema,
  ttl: z.number(),
});

const sendTargetSchema = z.object({
  thread_id: threadIdSchema,
  thread_type: threadTypeSchema,
  proactive: z.boolean(),
});

const mentionSchema = z.object({
  pos: z.number().int().min(0),
  uid: z.string().min(1).max(64),
  len: z.number().int().min(0),
});

export const MAX_MENTIONS = 20;

export const sendBodySchema = sendTargetSchema.extend({
  text: z.string().min(1),
  styles: z.array(styleSchema).optional(),
  quote: quoteSchema.optional(),
  mentions: z.array(mentionSchema).max(MAX_MENTIONS).optional(),
});

export const sendAttachmentBodySchema = sendTargetSchema.extend({
  filename: z.string().regex(/^[^/\\\0]{1,200}\.[A-Za-z0-9]{1,10}$/, "invalid filename"),
  data_base64: z.string().min(1),
  caption: z.string().default(""),
});

export const sendVideoBodySchema = sendTargetSchema.extend({
  video_url: z.string().min(1).max(2048),
  caption: z.string().default(""),
  /** Additive, optional: Zalo refuses a video card without a thumbnail (code 114 in the original's notes). */
  thumbnail_url: z.string().max(2048).optional(),
  duration_ms: z.number().int().min(0).optional(),
  width: z.number().int().min(1).optional(),
  height: z.number().int().min(1).optional(),
});

export const typingBodySchema = z.object({
  thread_id: threadIdSchema,
  thread_type: threadTypeSchema,
});

const receiptParamSchema = z.object({
  msgId: z.string().min(1),
  cliMsgId: z.string().min(1),
  uidFrom: z.string().min(1),
  idTo: z.string().min(1),
  msgType: z.string().min(1),
  st: z.number(),
  at: z.number(),
  cmd: z.number(),
  ts: z.union([z.string(), z.number()]),
});

/** MAX_MESSAGES_PER_SEND of zca-js (original `MAX_MESSAGES_PER_CALL`). */
export const MAX_RECEIPTS_PER_CALL = 50;

export const deliveredBodySchema = z.object({
  is_seen: z.boolean().default(false),
  params: z.array(receiptParamSchema).min(1).max(MAX_RECEIPTS_PER_CALL),
  thread_type: threadTypeSchema,
});

export const seenBodySchema = z.object({
  params: z.array(receiptParamSchema).min(1).max(MAX_RECEIPTS_PER_CALL),
  thread_type: threadTypeSchema,
});

export const reactionBodySchema = z.object({
  icon_key: z.string().min(1).max(32),
  msg_id: idLikeSchema,
  cli_msg_id: idLikeSchema,
  thread_id: threadIdSchema,
  thread_type: threadTypeSchema,
});

export const friendActionBodySchema = z.object({ uid: z.string().min(1).max(64) });
export const userInfoQuerySchema = z.object({ uid: z.string().min(1).max(64) });
export const groupInfoQuerySchema = z.object({ thread_id: threadIdSchema });

/**
 * The validated body satisfies zca-js' `Style` (start/len/st checked against the library's own
 * `TextStyle` values); only TypeScript cannot see through the discriminated union.
 */
export function toZcaStyles(
  styles: z.infer<typeof styleSchema>[] | undefined,
): Style[] | undefined {
  return styles as Style[] | undefined;
}

/**
 * zca-js' `SendMessageQuote` types `content` as a union of internal attachment shapes and `propertyExt`
 * as an exact object; the bridge forwards what the API sends (it got it from a listener Message), so the
 * shape is validated structurally above and cast here.
 */
export function toZcaQuote(
  quote: z.infer<typeof quoteSchema> | undefined,
): SendMessageQuote | undefined {
  return quote as SendMessageQuote | undefined;
}
