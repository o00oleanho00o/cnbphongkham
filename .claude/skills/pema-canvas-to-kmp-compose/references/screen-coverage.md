# Pema KMP screen coverage

Use this table when planning or reporting a port. It prevents saying “all screens are done” when only Flutter-backed screens were ported.

| Canvas group | Source | Current definition |
|---|---|---|
| A–H | Flutter | Mobile KMP port scope. Includes workspace by role, operational routes, care mode, and finance. **Ported and verified.** |
| I | `prototype/clinic-web` | Clinic web-only additions. **Ported and verified** (logic from web JS via `shared/clinic`). |
| J | `prototype/clinic-web` Patient 360 | Full web Patient 360 additions. **Ported and verified.** |
| K | `prototype/patient-mobile` | Patient web/mobile additions. **Ported and verified** (K3 merged into the E2 Journey tab). |

## Web-only group map (I/J/K)

| Codes | KMP file |
|---|---|
| I1–I4, I8, I9 | `feature/operations/OperationsGraph.kt` |
| I5, I7, I12 | `feature/patients/ClinicToolsScreens.kt` |
| I6 | `feature/aftercare/FollowUpInbox.kt` |
| I10, I11 | `feature/billing/InvoiceCashier.kt` |
| I13 | `feature/care/CareRecordScreen.kt` |
| J1–J5 | `feature/patients/Patient360Clinical.kt` |
| J6–J11 | `feature/patients/Patient360Admin.kt` |
| K1 | `feature/schedule/PatientAppointments.kt` |
| K2 | `feature/billing/PatientDocuments.kt` |
| K3 | `feature/workspace/WorkspaceGraph.kt` (care tab 1, `patientJourneyTimeline`) |

Web domain: `shared/clinic/` (`ClinicModels`, `ClinicSeed`, `ClinicStore`, `Operations`, `CrmCommands`, `*Commands.kt`). Seed parity test: `ClinicSeedParityTest`.

## Flutter-backed group map

| Group | Function | Primary KMP ownership |
|---|---|---|
| A | Clinic/owner workspace and account picker | `feature:workspace`, `composeApp` |
| B | Doctor workspace | `feature:workspace` |
| C | CSKH queue and search | `feature:care`, `feature:patients`, `feature:workspace` |
| D | Accountant workspace | `feature:workspace` |
| E | Pema Care/patient workspace | `feature:workspace` |
| F | Clinic operational detail routes | owning feature + app shell for F16/F17 |
| G | Pema Care detail routes | owning feature |
| H | Finance | `feature:finance` |

## Completion criteria for a canvas screen

- [ ] Route/tab/action is traceable to source logic.
- [ ] All source fields, text, state transitions and business restrictions are present.
- [ ] Role access is correct.
- [ ] JVM screenshot `shotVsCanvas("<ID>")` exists and was visually reviewed.
- [ ] Android flow was exercised where behavior can differ from JVM.

The status of a group must be reported separately as:

- **Ported and verified** — meets every criterion above.
- **Ported, device pending** — screenshot/build pass, no Android test yet.
- **Out of scope** — source is web-only or explicitly deferred.
- **Not started** — no KMP implementation.
