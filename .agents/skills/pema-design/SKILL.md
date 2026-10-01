---
name: pema-design
description: Design, implement, and review Pema Digital Clinic UI/UX for Clinic Web, Patient Mobile, and the mobile app (KMP + Compose Multiplatform, `pema-kmp/`); apply Pema identity, care flows, responsiveness, and business validation when adding or changing project screens.
---

# Pema Design

Design so staff can find the right patient, understand the work to do, and hand it off; patients know the next step. Keep Pema identity and business language consistent across web/native, while adapting layout by platform. This skill is for the Pema project; do not apply this style to other products.

## Read by task

- Designing color, type, icons, backgrounds, or components: [visual-system](references/visual-system.md).
- Adding screens, changing navigation, or changing business flows: [screens-and-flows](references/screens-and-flows.md).
- Fixing desktop/mobile/app layout: [platform-layout](references/platform-layout.md).
- Implementing, testing, and handing off: [delivery-and-review](references/delivery-and-review.md).

Source paths in references are relative to the repository root, not the skill directory. The skill is at `.agents/skills/pema-design/`; the shared guide is at `docs/23_PEMA_DESIGN_SKILL.md`. If only the standalone skill is available, use the design guidance inside it and ask for source when implementation must be verified; do not assume project files exist.

## Decisions to preserve

1. **Current Pema is blue/Be Vietnam Pro.** Local Pema logo; primary #0B4F94, navy #083A6E, sky #3CAAE5, background #F4F8FB. Manrope/teal in older documents is historical. Do not change the brand yourself based on a newly found sample UI.
2. **Patient 360 is the context bridge.** Related tasks must keep the correct patient/plan/order, show status and outcomes; a beautiful menu or card does not prove the business flow works.
3. **Desktop uses horizontal space; mobile stays task-focused.** Clinic Web standard is 1920×1020 CSS pixels at 100% zoom; do not lock the workspace into a narrow column. Mobile home only summarizes the next work; details open in child screens, not an endless page.
4. **Keep meaning; do not copy layout.** Web uses tables/resource calendars; native uses day-based lists, child screens, and short sheets. The app uses Compose Material 3 components from `core:ui`, safe areas, and push navigation, not a WebView wrapping the website.
5. **Separate data, design, and practical capability.** Draft differs from approved; payment does not mean treatment is complete. Web uses localStorage; the app keeps PB01 demo data in memory per process, state is patient-scoped; PB02 uses APIs. Read `pema-kmp/README.md` (status) before describing app features.
6. **Reference selectively.** Pema.vn is an identity reference; Annam images, Fastboy/Go Check In, and the design repo are cues for evaluation, not requirements to copy or add features. The care lifecycle drives design; CRM/loyalty/marketing is added only when it is in the assigned scope.

## How to work

Identify the user, platform, primary task, start/end states, and current source. Read `AGENT.md`, the PB01 set in order 0→1→2→3, and related documents; inspect the real screen if tools allow. Ask only when a missing decision would significantly affect the result.

When the user asks for analysis/planning, present findings and options before editing. When implementation has been requested, work through verification and handoff within scope; do not stop to request approval at every step. If the task is a review template, keep simulated sections explicit and do not expand into production backend work yourself.

For each new screen, define: entry point → context → primary action → validation → post-save state → handoff recipient → return path. Choose emphasis through hierarchy and spacing before adding color/cards/images. Reuse existing components and assets.

Test with meaningful data and suitable viewports; inspect both screenshots and interactions. State clearly what was run, what was not run, and any limits. Update Scope → Spec → Module Map → Architecture when scope/behavior changes, then README, guides, and SECTION_PROGRESS. The skill supports doing the work; it does not grant permission by itself to publish, send notifications, or push Git outside the user's request.


Mobile CRM02: use `docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md` as the current-state source. Finance lives inside the Clinic shell; native selects the role before the task, and must not cram CSKH/cashier/clinical into one shared home. Care prioritizes one next step; internal work and handoffs must not become patient messages.
