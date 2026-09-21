# Product scope V1

## Clinic web
Dashboard (meaningful queue counts), Today/Reception, patient search, Patient 360, consultation/note draft, treatment plan/session, Before/After Studio, Follow-up Inbox, light billing context.

## Patient mobile
Home/next action, appointments, treatment journey, progress/photos with consent, aftercare, medication, send update/photo, messages, documents, profile.

## Acceptance gates
1. Reception check-in → doctor sees same patient context.
2. Session complete → aftercare + follow-up task + patient app update.
3. Patient photo → clinic queue with unread/review/resolve state.
4. AI brief references real event IDs and shows doctor review.
5. Every screenshot/demo path uses synthetic data and labels demo mode.

## Exclusions
Accounting/warehouse/HR, autonomous diagnosis, production integrations, native app and real patient import.

## Pilot vs prototype boundary

The demo may simulate AI and use synthetic SVG photos with localStorage. Pilot additionally needs authentication/RBAC, consent retention, protected media, server audit/backup, validated templates, escalation SOP and channel integrations. A prototype PASS means the interaction demonstrates the intended flow; it does not make the deployment clinically ready.
