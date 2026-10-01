---
name: pema-canvas-to-kmp-compose
description: Port Pema screens from Flutter/web and the design canvas to KMP + Compose Multiplatform, 1:1 in both business logic and visuals. Use when asked to port Flutter to KMP/Compose, build Compose screens from the Pema App canvas, or check how closely KMP matches the canvas. Not for editing the canvas; use pema-web-to-canvas to update the canvas.
---

# Pema canvas → KMP + Compose Multiplatform

The KMP app lives in `pema-kmp/`; the Flutter source in `flutter-template/`; the visual source canvas is `Pema App redesign canvas/Pema App.dc.html`.

The goal is a **1:1 port**, not a “similar” UI:

| Source | Decides |
|---|---|
| Flutter `flutter-template/lib/` | business logic, data, role conditions, fields, buttons, states, routes, sheets, dialogs, snackbars |
| Canvas | colors, typography, spacing, radius, sizes, visual hierarchy and reference states |
| Pema web | only for porting screens marked web-only in the canvas (I/J/K) or when explicitly asked |

Never infer features from the canvas. Canvas I/J/K are web-only screens: logic comes from `prototype/` (web JS) through the `shared/clinic` domain, visuals follow the canvas; status and files are in [references/screen-coverage.md](references/screen-coverage.md).

Read first:

1. `pema-kmp/CONVENTIONS.md`
2. `AGENT.md`
3. `.agents/skills/pema-design/SKILL.md` and `references/visual-system.md`
4. `.claude/skills/pema-web-to-canvas/SKILL.md` if the scope involves the Pema web or the canvas.

## 1. Classify the scope before coding

**Read the spec first; don't re-read the web/canvas:** every screen has a spec + prompt at [`design-specs/screens/<ID>.md`](../../../design-specs/README.md) (or MCP `pema-design`: `get_screen(id)`, prompt `port_screen`). The spec contains the logic source (Flutter/web), route + KMP file, block → Compose layout, required sentences, rules, accepted differences and known gotchas. Only open source files for what the spec lacks; **when done, save anything new you learned** in `design-specs/notes.json` (or `record_note`) so it doesn't have to be found again.

List the canvas screen codes and trace each back to its source:

- **A–H** mirror Flutter screens; port them if the Flutter source has the matching route/tab/state.
- **I** Clinic operations from the web, **J** full web Patient 360, **K** web Pema Care: separate scope, not done just because A–H are done.
- Every modal, sheet, error/empty/loading state with its own canvas code is a screen to verify.

Minimum table:

| Code | Name | Logic source | KMP module | Route/state | Verification |
|---|---|---|---|---|---|
| F4 | Lên đơn | Flutter `quick_order` | `feature:orders` | `Routes.QuickOrder` | JVM shot + Android |

Don't start feature agents before this table is clear. Avoid two mistakes seen before: an imagined global bottom nav, and a pretty UI that lost the Flutter logic.

## 2. Canvas reference images

No manual screenshots: every module's `jvmTest` first runs the Gradle task `canvasRefs`, which calls [scripts/canvas-shots.cjs](scripts/canvas-shots.cjs) to render each canvas screen (390×844dp frame, ×2) into `pema-kmp/design-ref/<ID>.png`.

- Canvas unchanged → skipped immediately (Gradle up-to-date + hash in `design-ref/manifest.json`); canvas changed → all 82 screens are re-rendered (~25 s).
- The script starts design-viewer (vite, port 4180) if it isn't running and stops it afterwards; `CANVAS_URL` points at another viewer.
- Manual run: `node .claude\skills\pema-canvas-to-kmp-compose\scripts\canvas-shots.cjs [--force] [--only=I1,J3] [--out=<dir>]` or `.\gradlew.bat canvasRefs`.
- One-time setup: `npm install` in `design-viewer/` and `npx -y playwright@latest install chromium`. If missing, the task only warns; tests still run but produce no `-vs.png`.
- `design-ref/` is git-ignored (reproducible). Never commit reference images or `build/shots` images.
- Use `shotVsCanvas("F4") { ... }` in `jvmTest`; the side-by-side image is `<module>/build/shots/F4-vs.png` (canvas left, KMP right).

## 3. Design the architecture before porting

Keep module boundaries:

| Module | Responsibility |
|---|---|
| `core:common` | ASCII route IDs, `AppNavigator`, API config |
| `core:ui` | canvas tokens, Be Vietnam Pro font, shared blocks, scaffolds, sheets, snackbar, screenshot harness |
| `core:hardware` | expect/actual camera, gallery, print/launcher, haptics; fakes for tests |
| `shared` | models, repositories/stores, business state from Flutter providers |
| `feature:*` | route/screen composables and feature-only blocks |
| `composeApp` | NavHost, route guard, app container, root messenger |

Port domain/stores before UI. Compare Flutter JSON data with KMP: record count, products, role/sample data and business rules must match.

`Routes` only uses stable ASCII IDs. Vietnamese strings are titles/display text, not routes; URLs/routes with diacritics, spaces, `&` or special characters easily break navigation.

## 4. Build core UI from the canvas first

Don't let each feature create its own palette/cards/navigation. Port shared tokens and blocks first:

- Pema colors `blue #0B4F94`, `navy #083A6E`, `sky #3CAAE5`, `ink #17324D`, `muted #5D7184`, `paper #F4F8FB`, `line #E0EAF2`;
- Be Vietnam Pro from compose resources;
- heading, section, hero, metric, tile, notice, action/card/input/chip;
- `DetailScaffold` with app bar/back/max width and `PemaScaffold` with bottom nav/IME;
- icons from one Material family; surfaces/touch targets per the canvas.

If library assets don't reach the APK, check the convention plugin:

```kotlin
android {
    androidResources { enable = true }
}
```

Never replace canvas tokens with a “creative” palette. Screenshot at least one workspace/hero/reference before running feature waves.

## 5. Port navigation and role flows 1:1

Flutter uses push navigation: Workspace is the entry point; the bottom nav belongs to the workspace per role, not a global nav over every route.

The app shell needs to:

1. Start at Workspace.
2. Register feature routes in `NavHost`.
3. Apply permissions in `resolveRoute()` like Flutter: blocked routes open `DeniedScreen`; unknown routes open `GuideScreen`.
4. Keep tabs/groups/filters you can return to with `rememberSaveable`.
5. Parse routes with parameters (e.g. finance tab) through `Routes`.
6. Wrap `PaymentAlerts` at app level if Flutter wraps it at app level.

Always check Flutter roles and `allows()` before building menus. Test owner, doctor, care, accountant and patient/care mode separately.

## 6. Implement features in waves

Only run agents in parallel when module/file ownership doesn't overlap. Each agent must receive:

- the Flutter source paths and the feature's canvas codes;
- the list of fields/buttons/roles/states to keep;
- the `core:ui` APIs/blocks it may use;
- the files/modules it owns;
- a requirement to write `commonTest` for logic and `jvmTest` for screenshots;
- a requirement to build the feature before handing over.

Agents must not change `App.kt`, `Routes`, build logic, `FeatureDeps` or `core:ui` themselves; they report what integration should apply. After each wave, integration resolves cross-dependencies and runs the full build.

**Web-only screens (I/J/K):** two waves. Wave 0 (one agent): port the web data model (`data.js`, `operations-data.js`, `crm-*.js`, `care-finance.js`, `staff-context.js`) into `shared/clinic` with parity tests against `patients.json`; integration adds shared routes/permissions/`core:ui` blocks. Wave 1 (parallel agents): each agent owns one screen file + one `*Commands.kt` file in `shared/clinic` and exports a `NavGraphBuilder.xxxGraph(deps)` for integration to register. Keep the shared agent brief (rules + domain API) in one file so every agent reads the same source.

## 7. Required screenshot verification loop

For every ported canvas ID:

```kotlin
@Test
fun f4QuickOrder() {
    shotVsCanvas("F4") {
        QuickOrderScreen(state = previewState, onEvent = {})
    }
}
```

Process:

1. Render the shot at 390×844dp ×2.
2. Open `*-vs.png`; check text overflow, gutters, radius, font, icons, sheet/scrim and fixed bottom bars.
3. Fix until the layout matches; a passing test alone is not enough.
4. Cover every state the canvas has: default, filter, sheet/dialog, empty/error, role-specific.

Differences are only accepted with a clear reason, e.g. the real Pema logo instead of a placeholder, or real source sample data instead of canvas demo data.

## 8. Real Android verification (required)

JVM shots don't catch lifecycle, keyboard, bundle savers, asset packaging, navigation pops or nested scrolling.

```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
cd E:\Desktop\cnbphongkham\pema-kmp
.\gradlew.bat jvmTest :androidApp:assembleDebug --console=plain -q

$adb='E:\apdata\platform-tools\adb.exe'
& $adb devices -l
& $adb -s <serial> install -r androidApp\build\outputs\apk\debug\androidApp-debug.apk
& $adb -s <serial> shell monkey -p com.pema.clinic.kmp -c android.intent.category.LAUNCHER 1
```

Walk each role and critical action (open tab → child route → save → back → snackbar). Clear logcat before the run, then inspect the crash buffer. On multi-display emulators, use the right display ID in `screencap`.

If MIUI reports `INSTALL_FAILED_USER_RESTRICTED`, don't try to bypass it: the user must allow USB installs or copy the APK and install it on the device.

## 9. Compose gotchas confirmed on Android

| Problem | Fix |
|---|---|
| Snackbar lost on `save → back()` | Use `rememberPemaMessenger().show()` from the root scope provided in `App.kt`; the screen's `rememberCoroutineScope()` is cancelled on pop |
| Tab/filter/query lost after a child route | Use `rememberSaveable` |
| Custom data class/enum crashes when saving state | Provide a `listSaver` or `mapSaver`; never save non-Bundle-compatible objects directly |
| Crash inside a bottom sheet | Don't nest two `verticalScroll`s; only one scrolling area |
| Keyboard covers content/snackbar | `PemaScaffold` pads for the IME; Android manifest `windowSoftInputMode="adjustResize"`; don't add duplicate IME padding |
| Font/logo/resources missing from the APK | Enable `androidResources.enable = true` in the library module |
| Gradle build lock | Wait 30–60 s and rerun; don't run several full Gradle builds at once |
| Rotation resets the whole session | Stores must live outside composition (`AppStores`, per process); only rebuild `FeatureDeps` with the new activity's navigator/platform |
| Photo lost when Android recreates the activity while the camera is open | Don't revoke the URI grant / delete the file when the coroutine is cancelled; the new activity receives the result and emits it through `recoveredPhotos()`; clean temp files with `OnScreenCleared`, not `DisposableEffect` |
| Sent/saved photos left in `cache/photos` after the process is killed | Screens call `camera.markSaved(path)` when sending/saving; the Android layer keeps the draft photo list in saved state and, on the first camera service of each process, deletes every `pema_*` that is not a draft |
| Role/workspace reset after process death while another app (camera) was in front | Save the `Session` with the back stack (`RestoreSessionAfterProcessDeath` in `App.kt`) and restore it before `NavHost` composes |
| Tab switch takes ~2 s on a low-end phone (owner "Hồ sơ": 46 rows) | Long bodies are a `LazyColumn` (items keyed, filtering in `remember`), not `Column` + `verticalScroll` + `forEach`; embedded lists export `LazyListScope.xxxItems(...)` (e.g. `patientSearchItems`). Check speed on a release build and with `dumpsys gfxinfo <pkg> framestats`; pixel-diff the shots before/after |

## 10. Finish

1. Run `jvmTest :androidApp:assembleDebug`, count tests/failures from the XML.
2. Install and launch the APK on a real Android device or emulator; keep evidence screenshots outside the repo.
3. Compare with the coverage table: state exactly which groups/codes were ported, which web-only groups weren't, and the camera/iOS limits.
4. Update `pema-kmp/README.md` and `CONVENTIONS.md` if conventions or scope changed.
5. Record what you learned per screen in `design-specs/notes.json` (source functions, rules, differences, gotchas), then run `node .claude\skills\pema-canvas-to-kmp-compose\scripts\design-specs.cjs`; `--check` must pass.
6. If you changed anything visible on the Pema web, add a `Pending` entry in `.claude/skills/pema-web-to-canvas/web-changes.md`; don't update the canvas unless asked.
7. Never commit build images, APKs, local databases, screenshots or temp files.
