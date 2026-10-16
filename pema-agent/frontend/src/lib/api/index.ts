import type { components, paths } from "./schema";

/** DTOs generated from the BE OpenAPI (`make types`). Never edit schema.d.ts by hand. */
export type Schemas = components["schemas"];
export type ApiPaths = paths;

export type Role = Schemas["Role"];
export type ErrorCode = Schemas["ErrorCode"];
export type ErrorResponse = Schemas["ErrorResponse"];
export type CrmTask = Schemas["CrmTaskOut"];
