// Tests for src/zalo/reaction-icons.ts (the original had none).
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { Reactions } from "zca-js";
import { REACTION_ICON_KEYS, isReactionIconKey, toZaloReaction } from "./reaction-icons.js";

describe("reaction icons", () => {
  it("the_nine_keys_are_heart_like_haha_wow_ok_rose_kiss_cry_angry", () => {
    assert.deepEqual(REACTION_ICON_KEYS, ["heart", "like", "haha", "wow", "ok", "rose", "kiss", "cry", "angry"]);
  });

  it("each_key_maps_to_its_zalo_reaction", () => {
    assert.equal(toZaloReaction("heart"), Reactions.HEART);
    assert.equal(toZaloReaction("like"), Reactions.LIKE);
    assert.equal(toZaloReaction("haha"), Reactions.HAHA);
    assert.equal(toZaloReaction("wow"), Reactions.WOW);
    assert.equal(toZaloReaction("ok"), Reactions.OK);
    assert.equal(toZaloReaction("rose"), Reactions.ROSE);
    assert.equal(toZaloReaction("kiss"), Reactions.KISS);
    assert.equal(toZaloReaction("cry"), Reactions.CRY);
    assert.equal(toZaloReaction("angry"), Reactions.ANGRY);
  });

  it("an_unknown_key_falls_back_to_the_heart", () => {
    assert.equal(toZaloReaction("thumbs-sideways"), Reactions.HEART);
    assert.equal(toZaloReaction(""), Reactions.HEART);
  });

  it("a_key_that_exists_on_every_object_is_not_a_reaction", () => {
    assert.equal(isReactionIconKey("constructor"), false);
    assert.equal(toZaloReaction("toString"), Reactions.HEART);
  });
});
