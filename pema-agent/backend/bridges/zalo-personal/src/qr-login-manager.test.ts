// ported from: src/zalo/qr-login-manager.test.ts
// The first group keeps the original test names and cases (the original used a real database for the
// account store; the bridge has none). The second group is new: TTL, seq-supersede with abort, and the
// `declined` status.
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { doiChoDenKhi } from "./doi-cho-den-khi.js";
import { QrLoginManager, SESSION_TTL_MS, type QrLoginDeps } from "./qr-login-manager.js";
import { createFakeSession } from "./test-support.js";
import type { QrLoginEvent, ZaloSession } from "./zalo-types.js";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Login giả điều khiển được từng bước qua emit + resolve/reject */
function fakeLogin() {
  let emit!: (e: QrLoginEvent) => void;
  let resolve!: (api: ZaloSession) => void;
  let reject!: (err: Error) => void;
  let signal!: AbortSignal;
  const attached: string[] = [];

  const deps: Omit<QrLoginDeps, "now"> = {
    login: (_accountId, onEvent, abortSignal) => {
      emit = onEvent;
      signal = abortSignal;
      return new Promise<ZaloSession>((res, rej) => {
        resolve = res;
        reject = rej;
      });
    },
    attach: (accountId) => void attached.push(accountId),
    stopAccount: () => undefined,
  };
  return {
    deps,
    attached,
    emit: (e: QrLoginEvent) => emit(e),
    finish: () => resolve(createFakeSession()),
    fail: (msg: string) => reject(new Error(msg)),
    get signal() {
      return signal;
    },
  };
}

describe("qr-login-manager", () => {
  it("luồng chuẩn: starting -> waiting_scan (có QR) -> scanned -> success + attach", async () => {
    const fake = fakeLogin();
    const m = new QrLoginManager(fake.deps);
    m.startQrLogin("acc-qr-1", "clinic-a");
    assert.equal(m.getQrLoginStatus("acc-qr-1").state, "starting");

    fake.emit({ type: "qr", qrBase64: "QR_BASE64_DATA" });
    const waiting = m.getQrLoginStatus("acc-qr-1");
    assert.equal(waiting.state, "waiting_scan");
    assert.equal(waiting.qr_png_base64, "QR_BASE64_DATA");

    fake.emit({ type: "scanned" });
    assert.equal(m.getQrLoginStatus("acc-qr-1").state, "scanned");

    fake.finish();
    await doiChoDenKhi(() => m.getQrLoginStatus("acc-qr-1").state === "success", {
      moTa: "trạng thái chuyển sang success",
    });
    const done = m.getQrLoginStatus("acc-qr-1");
    assert.equal(done.state, "success");
    assert.equal(done.qr_png_base64, undefined, "QR phải bị xóa sau khi login xong");
    assert.deepEqual(fake.attached, ["acc-qr-1"]);
  });

  it("QR hết hạn: zca-js bắn lại QR mới, UI nhận ảnh mới", () => {
    const fake = fakeLogin();
    const m = new QrLoginManager(fake.deps);
    m.startQrLogin("acc-qr-2", "clinic-a");
    fake.emit({ type: "qr", qrBase64: "QR_CU" });
    fake.emit({ type: "expired" });
    fake.emit({ type: "qr", qrBase64: "QR_MOI" });

    const state = m.getQrLoginStatus("acc-qr-2");
    assert.equal(state.state, "waiting_scan");
    assert.ok(state.qr_png_base64?.includes("QR_MOI"));
  });

  it("từ chối trên điện thoại -> declined; login lỗi -> error kèm message", async () => {
    const fake1 = fakeLogin();
    const m = new QrLoginManager(fake1.deps);
    m.startQrLogin("acc-qr-3", "clinic-a");
    fake1.emit({ type: "declined" });
    assert.equal(m.getQrLoginStatus("acc-qr-3").state, "declined");

    const fake2 = fakeLogin();
    const m2 = new QrLoginManager(fake2.deps);
    m2.startQrLogin("acc-qr-4", "clinic-a");
    fake2.fail("mạng rớt");
    await doiChoDenKhi(() => m2.getQrLoginStatus("acc-qr-4").state === "error", {
      moTa: "trạng thái chuyển sang error",
    });
    const state = m2.getQrLoginStatus("acc-qr-4");
    assert.equal(state.state, "error");
    assert.equal(state.error, "mạng rớt");
  });

  it("phiên đang sống thì start lần 2 là idempotent (không tạo QR mới)", () => {
    const fake = fakeLogin();
    const m = new QrLoginManager(fake.deps);
    const first = m.startQrLogin("acc-qr-5", "clinic-a");
    fake.emit({ type: "qr", qrBase64: "QR_A" });

    const second = m.startQrLogin("acc-qr-5", "clinic-a");
    assert.equal(second.seq, first.seq, "phải trả về đúng phiên đang chạy");
  });

  it("phiên mới đè phiên chết: kết quả muộn của phiên cũ bị bỏ qua", async () => {
    const fake1 = fakeLogin();
    const fake2 = fakeLogin();
    // One manager, two scripted logins: the router hands out fake1 for the first session, fake2 after.
    let current = fake1;
    const routed = new QrLoginManager({
      login: (id, onEvent, signal) => current.deps.login(id, onEvent, signal),
      attach: (id, slug, session) => current.deps.attach(id, slug, session),
      stopAccount: () => undefined,
    });
    routed.startQrLogin("acc-qr-6", "clinic-a");
    fake1.emit({ type: "declined" }); // phiên 1 chết

    current = fake2;
    routed.startQrLogin("acc-qr-6", "clinic-a");
    fake2.emit({ type: "qr", qrBase64: "QR_PHIEN_2" });

    // Phiên 1 resolve muộn - không được đè trạng thái phiên 2
    fake1.finish();
    await sleep(10);
    const state = routed.getQrLoginStatus("acc-qr-6");
    assert.equal(state.state, "waiting_scan");
    assert.deepEqual(fake1.attached, [], "phiên cũ không được attach");
  });

  it("chưa từng start -> idle", () => {
    const m = new QrLoginManager(fakeLogin().deps);
    assert.equal(m.getQrLoginStatus("acc-chua-start").state, "idle");
  });
});

describe("QrLoginManager: session lifetime (new)", () => {
  it("a_session_that_is_not_scanned_within_three_minutes_times_out_and_its_login_is_aborted", () => {
    const clock = { now: 1_000_000 };
    const fake = fakeLogin();
    const manager = new QrLoginManager({ ...fake.deps, now: () => clock.now });
    manager.startQrLogin("acc-ttl", "clinic-a");
    fake.emit({ type: "qr", qrBase64: "QR" });

    clock.now += SESSION_TTL_MS - 1;
    assert.equal(manager.getQrLoginStatus("acc-ttl").state, "waiting_scan");

    clock.now += 1;
    assert.equal(manager.getQrLoginStatus("acc-ttl").state, "timeout");
    assert.equal(fake.signal.aborted, true, "zca-js must stop generating QR codes");
    assert.equal(manager.getQrLoginStatus("acc-ttl").state, "idle", "the timeout is reported once");
  });

  it("a_scanned_session_also_times_out_when_the_phone_never_confirms", () => {
    const clock = { now: 0 };
    const fake = fakeLogin();
    const manager = new QrLoginManager({ ...fake.deps, now: () => clock.now });
    manager.startQrLogin("acc-ttl-2", "clinic-a");
    fake.emit({ type: "scanned" });

    clock.now += SESSION_TTL_MS;

    assert.equal(manager.getQrLoginStatus("acc-ttl-2").state, "timeout");
  });

  it("starting_again_after_the_timeout_begins_a_new_session", () => {
    const clock = { now: 0 };
    const manager = new QrLoginManager({ ...fakeLogin().deps, now: () => clock.now });
    const first = manager.startQrLogin("acc-ttl-3", "clinic-a");
    clock.now += SESSION_TTL_MS;

    const second = manager.startQrLogin("acc-ttl-3", "clinic-a");

    assert.notEqual(second.seq, first.seq);
  });

  it("a_new_session_supersedes_the_old_one_by_seq_and_aborts_the_old_login", () => {
    const first = fakeLogin();
    let route = first;
    const manager = new QrLoginManager({
      login: (id, onEvent, signal) => route.deps.login(id, onEvent, signal),
      attach: () => undefined,
      stopAccount: () => undefined,
    });
    const oldSession = manager.startQrLogin("acc-seq", "clinic-a");
    first.emit({ type: "declined" });

    const second = fakeLogin();
    route = second;
    const newSession = manager.startQrLogin("acc-seq", "clinic-a");

    assert.equal(newSession.seq, oldSession.seq + 1);
    assert.equal(first.signal.aborted, true);
    first.emit({ type: "qr", qrBase64: "STALE" });
    assert.equal(
      manager.getQrLoginStatus("acc-seq").state,
      "starting",
      "events of the old session are ignored",
    );
  });

  it("a_declined_session_stays_declined_when_the_aborted_login_rejects", async () => {
    const fake = fakeLogin();
    const manager = new QrLoginManager(fake.deps);
    manager.startQrLogin("acc-declined", "clinic-a");
    fake.emit({ type: "declined" });

    fake.fail("QR login aborted");
    await sleep(10);

    assert.equal(manager.getQrLoginStatus("acc-declined").state, "declined");
  });

  it("a_running_account_is_stopped_before_a_new_qr_login_starts", () => {
    const stopped: string[] = [];
    const manager = new QrLoginManager({
      ...fakeLogin().deps,
      stopAccount: (id) => void stopped.push(id),
    });
    manager.startQrLogin("acc-relogin", "clinic-a");
    assert.deepEqual(stopped, ["acc-relogin"]);
  });

  it("the_clinic_slug_of_the_session_is_what_attach_receives", async () => {
    const attachedTo: string[] = [];
    const fake = fakeLogin();
    const manager = new QrLoginManager({
      ...fake.deps,
      attach: (_id, slug) => void attachedTo.push(slug),
    });
    manager.startQrLogin("acc-slug", "clinic-b");

    fake.finish();
    await doiChoDenKhi(() => attachedTo.length === 1, { moTa: "attach called" });

    assert.deepEqual(attachedTo, ["clinic-b"]);
  });
});
