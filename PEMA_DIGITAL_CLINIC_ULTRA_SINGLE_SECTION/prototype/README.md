# Pema Digital Clinic prototype

Two connected browser experiences share a mock dataset through `localStorage`:

- Clinic Web: `http://localhost:4173/clinic-web/`
- Patient Mobile: `http://localhost:4173/patient-mobile/`

Run from this folder with Python (no build or install step):

```powershell
python -m http.server 4173
```

Use the clinic sidebar to open Patient 360, record a session, and review follow-ups. Switch to the patient URL to see the same treatment journey and send an update. A reset button in the clinic header restores the deterministic demo data.
