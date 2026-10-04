import type { components, paths } from "./schema";

/** DTOs generated from the BE OpenAPI (`make types`). Never edit schema.d.ts by hand. */
export type Schemas = components["schemas"];
export type ApiPaths = paths;

export type Role = Schemas["Role"];
export type ErrorCode = Schemas["ErrorCode"];
export type ErrorResponse = Schemas["ErrorResponse"];
export type ReviewItem = Schemas["ReviewItemOut"];
export type CrmTask = Schemas["CrmTaskOut"];
export type ChannelSettings = Schemas["ChannelSettingsOut"];
export type Account = Schemas["AccountOut"];
export type Agent = Schemas["AgentOut"];
export type ScheduledJob = Schemas["ScheduledJob"];
export type KbSource = Schemas["KbSource"];
export type McpServer = Schemas["McpServerView"];
export type PolicyProfile = Schemas["PolicyProfile"];
