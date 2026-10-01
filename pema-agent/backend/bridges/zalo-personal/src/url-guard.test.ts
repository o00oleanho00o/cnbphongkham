// Tests of the send-video SSRF guard.
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { checkPublicHttpUrl, isPrivateAddress } from "./url-guard.js";

const publicHost = async (): Promise<string[]> => ["93.184.216.34"];

describe("isPrivateAddress", () => {
  const privateOnes = [
    "127.0.0.1",
    "10.0.0.1",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    "169.254.169.254",
    "100.64.0.1",
    "0.0.0.0",
    "224.0.0.1",
    "::1",
    "::",
    "fe80::1",
    "fc00::1",
    "fd12::1",
    "::ffff:127.0.0.1",
    "::ffff:10.0.0.1",
    "not-an-ip",
  ];
  privateOnes.forEach((address) => {
    it(`${address}_is_not_public`, () => {
      assert.equal(isPrivateAddress(address), true);
    });
  });

  ["93.184.216.34", "8.8.8.8", "172.32.0.1", "2606:2800:220:1:248:1893:25c8:1946"].forEach(
    (address) => {
      it(`${address}_is_public`, () => {
        assert.equal(isPrivateAddress(address), false);
      });
    },
  );
});

describe("checkPublicHttpUrl", () => {
  it("a_public_https_url_is_accepted", async () => {
    assert.deepEqual(await checkPublicHttpUrl("https://videos.example.test/a.mp4", publicHost), {
      ok: true,
    });
  });

  it("a_host_that_resolves_to_a_mix_with_a_private_address_is_refused", async () => {
    const mixed = async (): Promise<string[]> => ["93.184.216.34", "10.0.0.9"];
    const verdict = await checkPublicHttpUrl("https://videos.example.test/a.mp4", mixed);
    assert.equal(verdict.ok, false);
  });

  it("localhost_and_its_subdomains_are_refused_without_a_lookup", async () => {
    const neverCalled = async (): Promise<string[]> => {
      throw new Error("lookup must not run");
    };
    assert.equal((await checkPublicHttpUrl("http://localhost/a", neverCalled)).ok, false);
    assert.equal((await checkPublicHttpUrl("http://api.localhost/a", neverCalled)).ok, false);
  });

  it("an_ip_literal_in_the_url_is_judged_directly", async () => {
    assert.equal((await checkPublicHttpUrl("http://127.0.0.1:8200/v1", publicHost)).ok, false);
    assert.equal((await checkPublicHttpUrl("http://[::1]/v1", publicHost)).ok, false);
    assert.equal((await checkPublicHttpUrl("http://93.184.216.34/a.mp4", publicHost)).ok, true);
  });

  it("other_schemes_credentials_and_garbage_are_refused", async () => {
    assert.equal((await checkPublicHttpUrl("file:///etc/passwd", publicHost)).ok, false);
    assert.equal(
      (await checkPublicHttpUrl("https://u:p@videos.example.test/a", publicHost)).ok,
      false,
    );
    assert.equal((await checkPublicHttpUrl("not a url", publicHost)).ok, false);
  });

  it("a_host_that_does_not_resolve_is_refused", async () => {
    const failing = async (): Promise<string[]> => {
      throw new Error("ENOTFOUND");
    };
    assert.equal((await checkPublicHttpUrl("https://nowhere.example.test/a", failing)).ok, false);
    assert.equal(
      (await checkPublicHttpUrl("https://empty.example.test/a", async () => [])).ok,
      false,
    );
  });
});
