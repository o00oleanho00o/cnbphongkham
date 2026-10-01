import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ConfigError, loadConfig } from "./config.js";

const SECRET = "a-secret-of-sixteen+";

describe("config: environment of the bridge", () => {
  describe("given an empty environment", () => {
    it("the_bridge_is_disabled_by_default_with_the_documented_defaults", () => {
      const config = loadConfig({});
      assert.equal(config.enabled, false);
      assert.equal(config.host, "127.0.0.1");
      assert.equal(config.port, 8200);
      assert.equal(config.apiBaseUrl, "http://localhost:8000/api/v1");
      assert.equal(config.timezone, "Asia/Ho_Chi_Minh");
      assert.equal(config.maxProactivePerDayPerAccount, 100);
      assert.equal(config.maxSendsPerMinutePerAccount, 20);
      assert.equal(config.blockAfterRejectedSends, 5);
    });
  });

  describe("given the bridge is enabled", () => {
    it("boot_is_refused_without_a_secret", () => {
      assert.throws(() => loadConfig({ PEMA_ZALO_PERSONAL_ENABLED: "true" }), ConfigError);
    });

    it("boot_is_refused_with_a_secret_shorter_than_16_characters", () => {
      assert.throws(
        () => loadConfig({ PEMA_ZALO_PERSONAL_ENABLED: "true", PEMA_ZALO_BRIDGE_SECRET: "short" }),
        ConfigError,
      );
    });

    it("the_error_never_contains_the_secret", () => {
      const attempt = (): unknown =>
        loadConfig({ PEMA_ZALO_PERSONAL_ENABLED: "true", PEMA_ZALO_BRIDGE_SECRET: "tiny-secret" });
      assert.throws(attempt, (err: Error) => !err.message.includes("tiny-secret"));
    });

    it("a_secret_of_16_characters_is_accepted", () => {
      const config = loadConfig({
        PEMA_ZALO_PERSONAL_ENABLED: "1",
        PEMA_ZALO_BRIDGE_SECRET: SECRET,
      });
      assert.equal(config.enabled, true);
      assert.equal(config.secret, SECRET);
    });
  });

  describe("given overrides", () => {
    it("numbers_urls_and_time_zone_are_read", () => {
      const config = loadConfig({
        PEMA_ZALO_BRIDGE_PORT: "9001",
        PEMA_API_BASE_URL: "https://api.example.test/api/v1/",
        PEMA_BOT_TIMEZONE: "UTC",
        ZALO_BRIDGE_MAX_PROACTIVE_PER_DAY_PER_ACCOUNT: "7",
        ZALO_BRIDGE_MAX_SENDS_PER_MINUTE_PER_ACCOUNT: "3",
        ZALO_BRIDGE_BLOCK_AFTER_REJECTED_SENDS: "2",
        ZALO_BRIDGE_LOG_LEVEL: "debug",
      });
      assert.equal(config.port, 9001);
      assert.equal(config.apiBaseUrl, "https://api.example.test/api/v1");
      assert.equal(config.timezone, "UTC");
      assert.equal(config.maxProactivePerDayPerAccount, 7);
      assert.equal(config.maxSendsPerMinutePerAccount, 3);
      assert.equal(config.blockAfterRejectedSends, 2);
      assert.equal(config.logLevel, "debug");
    });

    it("an_invalid_number_or_time_zone_or_flag_is_refused", () => {
      assert.throws(() => loadConfig({ PEMA_ZALO_BRIDGE_PORT: "0" }), ConfigError);
      assert.throws(() => loadConfig({ PEMA_ZALO_BRIDGE_PORT: "70000" }), ConfigError);
      assert.throws(() => loadConfig({ ZALO_BRIDGE_BLOCK_AFTER_REJECTED_SENDS: "x" }), ConfigError);
      assert.throws(() => loadConfig({ PEMA_BOT_TIMEZONE: "Mars/Olympus" }), ConfigError);
      assert.throws(() => loadConfig({ PEMA_ZALO_PERSONAL_ENABLED: "maybe" }), ConfigError);
      assert.throws(() => loadConfig({ PEMA_API_BASE_URL: "not a url" }), ConfigError);
    });
  });
});
