// A small JSON Schema (draft-07) checker, just enough for tokens.schema.json: type, const, required,
// properties, additionalProperties (false or a schema), propertyNames.pattern, pattern, minLength and
// local `$ref` into `$defs`. It exists so the token test needs no extra dependency; it returns the list of
// problems (empty = valid) instead of throwing.

export type Schema = {
  type?: "object" | "string" | "number" | "integer" | "boolean" | "array";
  const?: unknown;
  required?: readonly string[];
  properties?: Record<string, Schema>;
  additionalProperties?: boolean | Schema;
  propertyNames?: { pattern?: string };
  pattern?: string;
  minLength?: number;
  $ref?: string;
  $defs?: Record<string, Schema>;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function matchesType(value: unknown, type: NonNullable<Schema["type"]>): boolean {
  const checks: Record<NonNullable<Schema["type"]>, (v: unknown) => boolean> = {
    object: isRecord,
    string: (v) => typeof v === "string",
    number: (v) => typeof v === "number",
    integer: (v) => Number.isInteger(v),
    boolean: (v) => typeof v === "boolean",
    array: Array.isArray,
  };
  return checks[type](value);
}

function resolve(root: Schema, schema: Schema): Schema {
  if (schema.$ref === undefined) return schema;
  const name = schema.$ref.replace("#/$defs/", "");
  const target = root.$defs?.[name];
  if (target === undefined) throw new Error(`unresolved $ref ${schema.$ref}`);
  return target;
}

function checkObject(
  root: Schema,
  schema: Schema,
  value: Record<string, unknown>,
  at: string,
): string[] {
  const missing = (schema.required ?? [])
    .filter((key) => !(key in value))
    .map((key) => `${at}: missing "${key}"`);
  const badNames = Object.keys(value)
    .filter(
      (key) =>
        schema.propertyNames?.pattern !== undefined &&
        !new RegExp(schema.propertyNames.pattern).test(key),
    )
    .map((key) => `${at}: property name "${key}" does not match ${schema.propertyNames?.pattern}`);
  const known = Object.entries(schema.properties ?? {}).flatMap(([key, sub]) =>
    key in value ? validateAt(root, sub, value[key], `${at}.${key}`) : [],
  );
  const extra = Object.entries(value).filter(([key]) => !(key in (schema.properties ?? {})));
  const extraProblems =
    schema.additionalProperties === false
      ? extra.map(([key]) => `${at}: unexpected "${key}"`)
      : isRecord(schema.additionalProperties)
        ? extra.flatMap(([key, v]) =>
            validateAt(root, schema.additionalProperties as Schema, v, `${at}.${key}`),
          )
        : [];
  return [...missing, ...badNames, ...known, ...extraProblems];
}

function validateAt(root: Schema, rawSchema: Schema, value: unknown, at: string): string[] {
  const schema = resolve(root, rawSchema);
  if (schema.const !== undefined && value !== schema.const)
    return [`${at}: expected ${String(schema.const)}`];
  if (schema.type !== undefined && !matchesType(value, schema.type))
    return [`${at}: expected ${schema.type}`];
  if (typeof value === "string") {
    const tooShort = schema.minLength !== undefined && value.length < schema.minLength;
    const noMatch = schema.pattern !== undefined && !new RegExp(schema.pattern).test(value);
    return [
      ...(tooShort ? [`${at}: shorter than ${schema.minLength}`] : []),
      ...(noMatch ? [`${at}: "${value}" does not match ${schema.pattern}`] : []),
    ];
  }
  return isRecord(value) ? checkObject(root, schema, value, at) : [];
}

export function validateJsonSchema(schema: Schema, value: unknown): string[] {
  return validateAt(schema, schema, value, "$");
}
