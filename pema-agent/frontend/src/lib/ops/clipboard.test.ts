import { describe, expect, it } from "vitest";

import { messageToCopy } from "./clipboard";

describe("message to copy", () => {
  it("the_quoted_message_is_copied_without_the_instruction", () => {
    expect(messageToCopy("Nhắn Zalo hỏi thăm: “Chào chị Hà, hôm nay da chị thế nào ạ?”")).toBe(
      "Chào chị Hà, hôm nay da chị thế nào ạ?",
    );
  });

  it("an_instruction_without_a_quote_is_copied_whole", () => {
    expect(messageToCopy("  Gọi hỏi thăm tình trạng da  ")).toBe("Gọi hỏi thăm tình trạng da");
  });

  it("a_very_short_quoted_word_is_not_mistaken_for_a_message", () => {
    expect(messageToCopy("Gọi khách “Hà” để hỏi lịch")).toBe("Gọi khách “Hà” để hỏi lịch");
  });
});
