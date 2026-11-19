import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/components/agent/pages/settings-page";

export const Route = createFileRoute("/_admin/admin/agent/settings/")({ component: SettingsPage });
