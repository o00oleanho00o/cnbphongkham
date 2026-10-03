// Icons the old Pema sidebar uses that the ported dashboard did not have. Same 24px / 1.7 stroke family
// as `components/admin/shared/dashboard-icons.tsx` (Lucide-style outlines).
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...props,
  };
}

export const IconCalendar = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="3.5" y="5" width="17" height="15.5" rx="3" />
    <path d="M8 3v4M16 3v4M3.5 10.5h17" />
  </svg>
);

export const IconStethoscope = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M6 3.5v5.2a4 4 0 0 0 8 0V3.5" />
    <path d="M10 12.7V14a5 5 0 0 0 10 0v-1.5" />
    <circle cx="20" cy="10.5" r="2" />
  </svg>
);

export const IconBell = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9Z" />
    <path d="M10 20a2 2 0 0 0 4 0" />
  </svg>
);

export const IconReceipt = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M6 3h12v18l-3-2-3 2-3-2-3 2Z" />
    <path d="M9 8h6M9 12h6" />
  </svg>
);

export const IconBanknote = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="3" y="6" width="18" height="12" rx="2.5" />
    <circle cx="12" cy="12" r="2.8" />
    <path d="M6.5 9.5v.01M17.5 14.5v.01" />
  </svg>
);

export const IconSparkles = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8Z" />
    <path d="M19 16v4M17 18h4" />
  </svg>
);

export const IconBook = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v14H6.5A1.5 1.5 0 0 0 5 18.5Z" />
    <path d="M5 18.5A1.5 1.5 0 0 0 6.5 20H19v-3" />
  </svg>
);

export const IconImages = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="3.5" y="4.5" width="14" height="14" rx="2.5" />
    <path d="m3.5 14.5 4-4 5 5" />
    <path d="M20.5 8v9a3 3 0 0 1-3 3H9" />
  </svg>
);
