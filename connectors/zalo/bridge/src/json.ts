/**
 * JSON that survives zca-js payloads. zca-js parses ids with `json-bigint`, so a listener `Message` or an
 * API result can hold a BigInt, which `JSON.stringify` refuses. BigInts are written as decimal strings.
 */
export function toJson(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) =>
    typeof item === "bigint" ? item.toString() : item,
  );
}
