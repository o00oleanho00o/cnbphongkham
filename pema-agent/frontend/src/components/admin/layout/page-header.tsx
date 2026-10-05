// ported from: web/src/layout/page-header.tsx
//
// Package U1: the title row is the kit's `PageHeading` (old Clinic Web `.page-heading`: bold navy title, grey
// subtitle, actions on the right). The icon tile of the ported header is gone, together with its `icon` prop:
// the old web has no icon on a page title; the sidebar already carries it.
"use client";

import type { ReactNode } from "react";

import { PageHeading } from "@/ui/workspace";

/** Header of a page: title + subtitle, optional slot on the right (`aside`: action buttons or a chip). */
export function PageHeader({
  title,
  subtitle,
  aside,
}: {
  title: string;
  subtitle: string;
  aside?: ReactNode;
}) {
  return <PageHeading title={title} subtitle={subtitle} actions={aside} />;
}
