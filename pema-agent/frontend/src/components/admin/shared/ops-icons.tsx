// Icons added for the Pema clinic screens (not in the original dashboard). Same 24px / 1.7 stroke
// family as `dashboard-icons.tsx` so they sit next to the ported icons without a visual seam.
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

export const IconClipboardCheck = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="5" y="4.5" width="14" height="16" rx="2.2" />
    <path d="M9 4.5V4a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 4v.5" />
    <path d="m9 13 2.2 2.2L15.5 11" />
  </svg>
);

export const IconInbox = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M3.5 13.5 6 5.8A2 2 0 0 1 7.9 4.5h8.2a2 2 0 0 1 1.9 1.3l2.5 7.7" />
    <path d="M3.5 13.5v4.2a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-4.2h-5.3a3.2 3.2 0 0 1-6.4 0Z" />
  </svg>
);

export const IconShieldCheck = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3.2 5 5.8v5.6c0 4.3 2.8 8 7 9.4 4.2-1.4 7-5.1 7-9.4V5.8Z" />
    <path d="m9 12 2.2 2.2L15.2 10" />
  </svg>
);

export const IconUser = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="8.5" r="3.6" />
    <path d="M4.8 20c.9-3.6 3.7-5.4 7.2-5.4s6.3 1.8 7.2 5.4" />
  </svg>
);

export const IconCopy = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="8.5" y="8.5" width="11" height="11" rx="2.2" />
    <path d="M15.5 8.5V6.7a2.2 2.2 0 0 0-2.2-2.2H6.7a2.2 2.2 0 0 0-2.2 2.2v6.6a2.2 2.2 0 0 0 2.2 2.2h1.8" />
  </svg>
);

export const IconFlag = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M5.5 21V4.2M5.5 4.8c3-1.7 5.2 1.6 8.2 0 1.8-.9 3.4-.9 4.8-.2v8c-1.4-.7-3-.7-4.8.2-3 1.6-5.2-1.7-8.2 0" />
  </svg>
);

export const IconRefresh = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M20 11.5A8 8 0 0 0 5.8 7M4 4.5V8h3.5M4 12.5A8 8 0 0 0 18.2 17M20 19.5V16h-3.5" />
  </svg>
);

export const IconPower = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3.5v8.2M7.2 6.6a7.5 7.5 0 1 0 9.6 0" />
  </svg>
);

export const IconPhone = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M6.6 3.8h2.7l1.3 3.6-1.7 1.2a10.4 10.4 0 0 0 4.5 4.5l1.2-1.7 3.6 1.3v2.7a1.9 1.9 0 0 1-2 1.9A13.8 13.8 0 0 1 4.7 5.8a1.9 1.9 0 0 1 1.9-2Z" />
  </svg>
);

export const IconChevronLeft = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="m14.5 6-6 6 6 6" />
  </svg>
);

export const IconImageOff = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="3.5" y="4.5" width="17" height="15" rx="2.4" />
    <circle cx="9" cy="10" r="1.6" />
    <path d="m4 18 5-5 3 3 3-3 5 5M3.5 3.5l17 17" />
  </svg>
);

export const IconIdBadge = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="4.5" y="3.5" width="15" height="17" rx="2.4" />
    <circle cx="12" cy="10" r="2.4" />
    <path d="M8.2 17c.6-1.8 2-2.8 3.8-2.8s3.2 1 3.8 2.8" />
  </svg>
);
