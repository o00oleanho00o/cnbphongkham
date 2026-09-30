# Pema identity and visual system

Baseline summarized from the web and Flutter cycle on 2026-09-22; this is the project's design convention, not a claim to be the official brand manual. When tokens/code intentionally change, update this reference together with the UI docs.

## Color and contrast

| Token | Value | Role |
|---|---|---|
| Primary | #0B4F94 | Main CTA, active navigation, clickable links |
| Navy | #083A6E | Strong identity areas, emphasized headings |
| Sky | #3CAAE5 | Graphic details, light highlights; not the default background for small white text |
| Ink | #17324D | Main content |
| Muted | #5D7184 | Metadata/notes that remain readable |
| Paper | #F4F8FB | App background |
| Surface | #FFFFFF | Forms, profiles, content needing focus |

Status colors for success/warning/error come from existing semantic tokens/components after contrast is checked; do not use brand blue for every status yourself. Text/icon labels must distinguish status even without color vision. Measure contrast on the real background: target WCAG AA 4.5:1 for normal text, 3:1 for large text; check focus and control boundaries. Do not write “accessibility passed” just because Material is used.

Hierarchy: light background → white surface → clear text → one prominent action. Limit competing gradients, shadows, and badges; avoid turning clinical tables into marketing dashboards. Identity may be strong in hero areas, but data rows should stay calm and easy to scan.

## Font, icon, spacing

- Local Be Vietnam Pro for Vietnamese; regular/medium/semibold/bold. Do not fall back to Times/Georgia in inputs/headings. Keep the OFL license and verify the font actually loads.
- Native starting point: body 14–16, label 12, heading about 25 logical pixels; adjust by hierarchy, not by shrinking text to cram content. Web desktop heading around 30 when suitable for the current layout. Test long Vietnamese names, prices, and multi-line notes.
- Spacing scale 4/8/12/16/20/24. Group information through proximity/alignment; do not wrap every label in a card. Native card radius 18, hero 24, controls by the current theme (14); do not mechanically apply every native radius to web.
- Web uses consistent Lucide SVG (20px/stroke 1.7 baseline in the current system); native uses Material outlined. Do not mix random emoji/Unicode as business icons. Icon-only controls need an accessible name/tooltip when appropriate; decorative icons must not duplicate screen-reader content.
- Native touch target minimum is 48 logical pixels; check button spacing, disabled/loading states, and hit area instead of only the icon stroke size.

## Logo, images, and backgrounds

Original web assets are in `prototype/shared/assets/`: `pema-logo.png`, font `be-vietnam-pro-*`, `care-waves.svg`, Lucide icons/license. Flutter uses `flutter-template/assets/` declared in pubspec. Reuse existing assets; do not duplicate a new brand kit inside the skill.

Preserve logo ratio and breathing room; do not stretch it, recolor it, or place it on a low-contrast background. Light blue waves are only for hero/identity areas, not behind tables, prescriptions, or doctor notes. A beautiful background must help focus, not hide text or make home longer.

Simulated patient/Before–After photos must have illustrative context; do not use AI images as treatment evidence, and do not score effectiveness from placeholders. Do not put real records into screenshots. Generate images only when existing assets do not solve a specific need; this is not a mandatory step.

Short suggested prompt when a background image is requested: “Create an abstract background for Pema Clinic & Care: white and blue #0B4F94/#3CAAE5, very light soft wave lines, wide empty space for text, clean and calm; no text, no logo, no people, no treatment-result images; ratio [by placement].” Overlay text/logo in UI to keep quality and responsiveness.

## When referencing other designs

Record the problem being solved → useful pattern → adaptation for Pema → how to check. Do not copy the Annam/Fastboy brand. “Owning the customer lifecycle” becomes a care flow with handoff; do not turn the app into an advertising tool or add loyalty unless requested.

Orientation sources already used in the project: https://pema.vn/ ; https://github.com/Dammyjay93/interface-design ; https://github.com/vercel-labs/agent-skills . There is no need to fetch these sources again for every small change; source/tokens and approved decisions in the repo are the implementation baseline.
