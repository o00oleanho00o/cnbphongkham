# Pema KMP screen coverage

Use this table when planning or reporting a port. It prevents saying “all screens are done” when only Flutter-backed screens were ported.

| Canvas group | Source | Current definition |
|---|---|---|
| A–H | Flutter | Mobile KMP port scope. Includes workspace by role, operational routes, care mode, and finance. |
| I | `prototype/clinic-web` | Clinic web-only additions. Separate scope from Flutter parity. |
| J | `prototype/clinic-web` Patient 360 | Full web Patient 360 additions. Separate scope from Flutter parity. |
| K | `prototype/patient-mobile` | Patient web/mobile additions. Separate scope from Flutter parity. |

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
