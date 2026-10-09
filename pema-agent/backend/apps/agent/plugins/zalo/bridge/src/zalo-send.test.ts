// Tests for `duongGuiZcaJs` / `laLoiMayChuTuChoi` (ported from send-reply-in-parts.ts; the original tests of
// that file cover the splitting and retry logic that lives in the Python API) and the attachment builder.
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { TextStyle, ZaloApiError, type SendMessageQuote } from "zca-js";
import { createFakeApi } from "./test-support.js";
import { buildAttachmentSource, duongGuiZcaJs, laLoiMayChuTuChoi } from "./zalo-send.js";

const QUOTE = { msgId: "m1", uidFrom: "2000001", content: "gốc" } as unknown as SendMessageQuote; // synthetic

describe("duongGuiZcaJs", () => {
  it("styles_are_attached_only_when_non_empty", async () => {
    const fake = createFakeApi();
    const send = duongGuiZcaJs(fake.api, "2000001", 0);

    await send({ text: "a", styles: [] });
    await send({ text: "b", styles: [{ start: 0, len: 1, st: TextStyle.Bold }] });

    assert.deepEqual(
      fake.callsTo("sendMessage").map((call) => call.args[0]),
      [{ msg: "a" }, { msg: "b", styles: [{ start: 0, len: 1, st: "b" }] }],
    );
  });

  it("a_quote_is_attached_only_when_present", async () => {
    const fake = createFakeApi();
    const send = duongGuiZcaJs(fake.api, "2000001", 1);

    await send({ text: "a" });
    await send({ text: "b", quote: QUOTE });

    assert.deepEqual(
      fake.callsTo("sendMessage").map((call) => call.args[0]),
      [{ msg: "a" }, { msg: "b", quote: QUOTE }],
    );
  });

  it("mentions_are_attached_only_when_non_empty", async () => {
    const fake = createFakeApi();
    const send = duongGuiZcaJs(fake.api, "3000001", 1);

    await send({ text: "a", mentions: [] });
    await send({ text: "b", mentions: [{ pos: 0, uid: "2000002", len: 3 }] });

    assert.deepEqual(
      fake.callsTo("sendMessage").map((call) => call.args[0]),
      [{ msg: "a" }, { msg: "b", mentions: [{ pos: 0, uid: "2000002", len: 3 }] }],
    );
  });

  it("the_thread_id_and_type_are_passed_through", async () => {
    const fake = createFakeApi();
    await duongGuiZcaJs(fake.api, "3000001", 1)({ text: "a" });
    assert.deepEqual(fake.callsTo("sendMessage")[0]?.args.slice(1), ["3000001", 1]);
  });
});

describe("laLoiMayChuTuChoi", () => {
  it("an_error_with_a_numeric_code_is_a_server_rejection", () => {
    assert.equal(laLoiMayChuTuChoi(new ZaloApiError("rejected", 112)), true);
  });

  it("errors_without_a_numeric_code_are_transport_failures", () => {
    assert.equal(laLoiMayChuTuChoi(new Error("ETIMEDOUT")), false);
    assert.equal(laLoiMayChuTuChoi(new ZaloApiError("no code")), false);
    assert.equal(laLoiMayChuTuChoi(null), false);
    assert.equal(laLoiMayChuTuChoi({ code: "112" }), false);
  });
});

describe("buildAttachmentSource", () => {
  const TINY_PNG = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "base64",
  );

  it("a_png_gets_its_measured_size_and_byte_count", () => {
    const source = buildAttachmentSource("anh.png", TINY_PNG);
    assert.deepEqual(source.metadata, { totalSize: TINY_PNG.byteLength, width: 1, height: 1 });
  });

  it("a_document_only_gets_its_byte_count", () => {
    const source = buildAttachmentSource("tai-lieu.pdf", Buffer.from("abc"));
    assert.deepEqual(source.metadata, { totalSize: 3 });
  });

  it("an_image_that_cannot_be_measured_still_gets_its_byte_count", () => {
    const source = buildAttachmentSource("hong.jpg", Buffer.from("not an image"));
    assert.deepEqual(source.metadata, { totalSize: 12 });
  });
});
