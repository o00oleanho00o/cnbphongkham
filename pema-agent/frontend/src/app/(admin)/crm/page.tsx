"use client";

// "Vòng đời khách hàng" (`/crm`): what the old CRM01 workspace had that Today, Patient 360, Inbox and Review do not
// show. Three tabs: the customer groups (new, returning, treating, dormant, reactivated, at risk) with the marketing
// opt-out switch, the contact log (outcome and channel), and the automation rules as read-only text. The queue and
// the resolve sheet are `/today`; the day's KPI are `/dashboard`; the clinical and CRM panels are Patient 360.
import { useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { ActivitiesPanel } from "@/components/ops/crm/activities-panel";
import { RulesPanel } from "@/components/ops/crm/rules-panel";
import { SegmentsPanel } from "@/components/ops/crm/segments-panel";
import { TabPanel, Tabs, type TabItem } from "@/ui/tabs";

const TABS: readonly TabItem[] = [
  { id: "segments", label: "Nhóm khách" },
  { id: "activities", label: "Nhật ký chăm sóc" },
  { id: "rules", label: "Quy tắc tự động" },
];

const ID_PREFIX = "crm";

export default function CrmPage() {
  const [tab, setTab] = useState("segments");

  return (
    <div>
      <PageHeader
        title="Vòng đời khách hàng"
        subtitle="Khách đang ở giai đoạn nào, đã được chăm sóc thế nào và quy tắc nào tạo việc"
      />
      <Tabs
        label="Vòng đời khách hàng"
        idPrefix={ID_PREFIX}
        items={TABS}
        value={tab}
        onChange={setTab}
      />
      <TabPanel idPrefix={ID_PREFIX} id="segments" value={tab}>
        <SegmentsPanel />
      </TabPanel>
      <TabPanel idPrefix={ID_PREFIX} id="activities" value={tab}>
        <ActivitiesPanel />
      </TabPanel>
      <TabPanel idPrefix={ID_PREFIX} id="rules" value={tab}>
        <RulesPanel />
      </TabPanel>
    </div>
  );
}
