import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  MAX_CLOCK_SKEW_SECONDS,
  SIGNATURE_HEADER,
  TIMESTAMP_HEADER,
  computeSignature,
  signedHeaders,
  verifySignature,
} from "./auth.js";

const SECRET = "known-secret-0123456789";
const NOW = 1_700_000_000;
const BODY = JSON.stringify({ a: 1 });

function verify(overrides: Partial<Parameters<typeof verifySignature>[0]> = {}) {
  const headers = signedHeaders(SECRET, BODY, NOW);
  return verifySignature({
    secret: SECRET,
    timestamp: headers[TIMESTAMP_HEADER],
    signature: headers[SIGNATURE_HEADER],
    body: BODY,
    nowSeconds: NOW,
    ...overrides,
  });
}

describe("auth: HMAC of the wire protocol", () => {
  describe("given the documented signing rule", () => {
    it("signature_matches_the_known_vector_of_hmac_sha256_over_timestamp_dot_body", () => {
      // Vector computed independently with `openssl`-style HMAC-SHA256 over "1700000000.{"a":1}".
      assert.equal(
        computeSignature(SECRET, String(NOW), BODY),
        "df476fcb172f72dd29d4c7dcb4289d203dfb7cc2fa0a174ef1de21918ae9f5ba",
      );
    });

    it("an_empty_body_signs_the_empty_string", () => {
      assert.equal(
        computeSignature(SECRET, String(NOW), ""),
        "9dcbdf82ad8bd873c6a839fc966f2baefc942c983fd6e52eda64f991dac1885f",
      );
    });

    it("string_and_byte_bodies_give_the_same_signature", () => {
      const bytes = new TextEncoder().encode(BODY);
      assert.equal(
        computeSignature(SECRET, String(NOW), bytes),
        computeSignature(SECRET, String(NOW), BODY),
      );
    });
  });

  describe("given a request signed by the other side", () => {
    it("a_valid_signature_is_accepted", () => {
      assert.deepEqual(verify(), { ok: true });
    });

    it("a_signature_made_with_another_secret_is_refused", () => {
      const forged = signedHeaders("another-secret-0123456789", BODY, NOW);
      const result = verify({ signature: forged[SIGNATURE_HEADER] });
      assert.deepEqual(result, { ok: false, reason: "bad_signature" });
    });

    it("a_tampered_body_is_refused", () => {
      assert.deepEqual(verify({ body: JSON.stringify({ a: 2 }) }), {
        ok: false,
        reason: "bad_signature",
      });
    });

    it("a_tampered_timestamp_is_refused", () => {
      assert.deepEqual(verify({ timestamp: String(NOW + 1) }), {
        ok: false,
        reason: "bad_signature",
      });
    });

    it("a_signature_that_is_not_64_hex_characters_is_refused", () => {
      assert.deepEqual(verify({ signature: "abc" }), { ok: false, reason: "bad_signature" });
    });

    it("missing_headers_are_refused", () => {
      assert.deepEqual(verify({ signature: undefined }), { ok: false, reason: "missing_headers" });
      assert.deepEqual(verify({ timestamp: null }), { ok: false, reason: "missing_headers" });
    });

    it("a_timestamp_that_is_not_an_integer_is_refused", () => {
      assert.deepEqual(verify({ timestamp: "17e8" }), { ok: false, reason: "bad_timestamp" });
    });
  });

  describe("given the clock window", () => {
    it("a_timestamp_exactly_at_the_limit_is_accepted_in_both_directions", () => {
      const past = signedHeaders(SECRET, BODY, NOW - MAX_CLOCK_SKEW_SECONDS);
      const future = signedHeaders(SECRET, BODY, NOW + MAX_CLOCK_SKEW_SECONDS);
      assert.equal(
        verify({ timestamp: past[TIMESTAMP_HEADER], signature: past[SIGNATURE_HEADER] }).ok,
        true,
      );
      assert.equal(
        verify({ timestamp: future[TIMESTAMP_HEADER], signature: future[SIGNATURE_HEADER] }).ok,
        true,
      );
    });

    it("a_stale_timestamp_is_refused_even_with_a_correct_signature", () => {
      const stale = signedHeaders(SECRET, BODY, NOW - MAX_CLOCK_SKEW_SECONDS - 1);
      const result = verify({
        timestamp: stale[TIMESTAMP_HEADER],
        signature: stale[SIGNATURE_HEADER],
      });
      assert.deepEqual(result, { ok: false, reason: "stale_timestamp" });
    });

    it("a_timestamp_too_far_in_the_future_is_refused", () => {
      const early = signedHeaders(SECRET, BODY, NOW + MAX_CLOCK_SKEW_SECONDS + 1);
      const result = verify({
        timestamp: early[TIMESTAMP_HEADER],
        signature: early[SIGNATURE_HEADER],
      });
      assert.deepEqual(result, { ok: false, reason: "stale_timestamp" });
    });
  });
});
