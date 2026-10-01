// New test: the Zalo credential and the QR live in memory only. The bridge writes nothing to disk while an
// account starts, a QR login completes and messages are sent and received.
import assert from "node:assert/strict";
import fs from "node:fs";
import fsp from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import { createBridge } from "./bridge.js";
import { doiChoDenKhi } from "./doi-cho-den-khi.js";
import {
  FakeGateway,
  RecordingPublisher,
  SECRET,
  TEST_CREDENTIAL,
  createFakeApi,
  createFakeSession,
  fakeUserMessage,
  makeConfig,
  readEnvelope,
  signedSender,
} from "./test-support.js";

describe("credential handling: nothing is written to disk", () => {
  let workDir = "";
  let originalCwd = "";
  const writes: string[] = [];

  beforeEach(() => {
    originalCwd = process.cwd();
    workDir = fs.mkdtempSync(path.join(os.tmpdir(), "zalo-bridge-no-disk-"));
    process.chdir(workDir);
    writes.length = 0;
    const record =
      (name: string) =>
      (): void => {
        writes.push(name);
      };
    mock.method(fs, "writeFileSync", record("writeFileSync"));
    mock.method(fs, "appendFileSync", record("appendFileSync"));
    mock.method(fs, "mkdirSync", record("mkdirSync"));
    mock.method(fs, "createWriteStream", () => {
      writes.push("createWriteStream");
      throw new Error("no file writes expected");
    });
    mock.method(fsp, "writeFile", async () => void writes.push("writeFile"));
    mock.method(fsp, "appendFile", async () => void writes.push("appendFile"));
  });

  afterEach(() => {
    mock.restoreAll();
    process.chdir(originalCwd);
    fs.rmSync(workDir, { recursive: true, force: true });
  });

  it("start_qr_login_sends_and_incoming_messages_leave_the_working_directory_empty", async () => {
    // Given a bridge with a fake gateway
    const gateway = new FakeGateway();
    const publisher = new RecordingPublisher();
    const bridge = createBridge({ config: makeConfig(), gateway, publisher });
    const sender = signedSender(bridge.app, SECRET);
    const fake = createFakeApi();
    gateway.nextSessions.push(createFakeSession(fake));

    // When the API starts an account with a credential, a message arrives and a reply is sent
    await sender.post("/v1/accounts/acc-1/start", { clinic_slug: "clinic-a", credential: TEST_CREDENTIAL });
    fake.listener.emitMessage(fakeUserMessage());
    await sender.post("/v1/accounts/acc-1/send", {
      thread_id: "2000001",
      thread_type: 0,
      text: "Chào bạn",
      proactive: false,
    });
    await sender.post("/v1/accounts/acc-2/login/qr", { clinic_slug: "clinic-a" });
    gateway.qrControls[0]?.emit({ type: "qr", qrBase64: "QR_PNG_BASE64" });
    gateway.qrControls[0]?.succeed(createFakeSession(createFakeApi(), "1000099"));
    await doiChoDenKhi(
      async () => (await readEnvelope(await sender.get("/v1/accounts/acc-2/login/qr")))["state"] === "success",
      { moTa: "QR login success" },
    );

    // Then nothing was written anywhere
    assert.deepEqual(writes, []);
    assert.deepEqual(fs.readdirSync(workDir), []);
  });
});
