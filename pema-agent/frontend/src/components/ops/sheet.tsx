"use client";

// The bottom sheet / dialog of the clinic screens now lives in the design kit (`src/ui/dialog.tsx`), with
// the same props and the same backdrop rule; this path stays so the screens that import it do not change.
export { Sheet } from "@/ui/dialog";
