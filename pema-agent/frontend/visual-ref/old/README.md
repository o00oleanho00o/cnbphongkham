# visual-ref/old: reference screenshots of the old Pema Clinic Web

The images here are generated, not committed (git-ignored). They are what the new screens are compared with
side by side: same structure (sidebar width, header, columns), not pixel equality.

## Produce them

The old web is static and read-only for this package. Serve it, then run its own capture script with the
output directory pointed here:

```
python -m http.server 4173 --bind 127.0.0.1 --directory prototype
PEMA_EVIDENCE_DIR=pema-agent/frontend/visual-ref/old node prototype/review-desktop.cjs
```

`prototype/review-desktop.cjs` loads Playwright from a path on the machine of its author. On another machine
run a copy of the script (outside the repository) whose first line requires the Playwright of
`pema-agent/frontend/node_modules` instead; do not edit the original.

It writes `<width>-<screen>.png` for 11 screens (dashboard, today, schedule, patients, followups, studio,
resources, services, cashier, ask, guide) and 5 Patient 360 tabs (overview, consult, plan, session, photos)
at 1920x1020, 1440x900, 1280x720, 1024x768 and 390x844, plus `results.json` (overflow check of the old web).

## Compare

The new screenshots come from `pnpm visual` (see `../new/README.md`). The check that U0 signs is `/today`
at 1920x1020: `1920-today.png` here against `1920x1020-today.png` there.

The old web shows synthetic demo patients only; nothing here may contain real patient data.
