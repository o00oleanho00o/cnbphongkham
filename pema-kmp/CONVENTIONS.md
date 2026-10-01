# pema-kmp conventions (KMP + Compose Multiplatform)

The Pema mobile app in Kotlin Multiplatform + Compose Multiplatform (Android, iOS).
- **Business logic, display text, screen flows**: the KMP code (`shared`, `feature:*`) is the source of truth for the core screens (A–H); web-sourced screens (I/J/K) follow `prototype/`. When changing a screen keep every field, button, enable/disable condition, snackbar, dialog, sheet and role-based visibility.
- **Visuals**: the design canvas `Pema App redesign canvas/Pema App.dc.html` is the source of truth — the CSS of each block (size, padding, radius, color, font size/weight) and the reference image of each screen (A1…K3). Per-screen specs: `design-specs/screens/<ID>.md`.

## Modules & ownership

| Module | Content | Owner |
|---|---|---|
| `core:common` | `Routes` (ASCII id + `Routes.titleOf(id)` = screen title, `finance(tab)`, `guide(title)`, `denied(title)`), `AppNavigator`, `AsyncUiState`, `ApiConfig`, Ktor `HttpClientFactory` | integration |
| `core:ui` | Design system built 1:1 from the canvas CSS: `PemaColors`, `PemaTheme`/`PemaType` (Be Vietnam Pro), `PemaIcon` (Material Icons font), blocks (`PemaHeading`, `PemaHero`, `PemaMetrics`, `PemaActions`, `PemaTile`, `PemaNotice`, `PemaPrimary`…), controls (button, field, dropdown, chip, checkbox), `DetailScaffold`, `PemaMainTopBar`, `PemaBottomNav`, sheet/dialog/snackbar, `LocalPhoto`, `moneyFormat`; jvmMain: screenshot harness `shots/Shots.kt` | integration |
| `core:hardware` | `PlatformServices` (camera, images, printer, launcher, haptics, notifier), `LocalPlatformServices`, `FakePlatformServices` | hardware |
| `shared` | domain + state (session, catalog, patients, orders, billing, care, review queue, finance) | domain |
| `feature:<x>` | screens + ViewModels + the feature's own blocks | that feature's agent |
| `composeApp` | `App.kt` (NavHost, route guard, Guide fallback, snackbar, `PaymentAlerts` around the navigator), `AppContainer.kt` | integration |
| `androidApp` | `MainActivity` (edge-to-edge), manifest, icon | integration |

Rules:
- Features only depend on `core:*` and `shared`. Exceptions: `feature:workspace` embeds `CareQueue` (`feature:care`) and `PatientSearch` (`feature:patients`); the app shell calls `PaymentAlerts` (`feature:finance`).
- Don't edit files outside what you own. Changes to `FeatureDeps`, `AppContainer`, `App.kt`, `Routes`, `core:ui` or build files → put them in your report; integration applies them.
- Each feature exports `fun NavGraphBuilder.<name>Graph(deps: FeatureDeps)` and registers `composable(Routes.X)` for its routes. Always navigate through `deps.navigator.go(...)`: the shell applies the role guard (screen "Tác vụ không thuộc không gian hiện tại…"), unknown routes → Guide, `/finance` + its sub-pages are not guarded.

## Adding a screen
1. `feature/<x>/src/commonMain/kotlin/com/pema/clinic/feature/<x>/<Name>Screen.kt` — a stateless `@Composable` taking state + callbacks (so screenshot tests can pass fake state), plus a `…Route(vm)` wrapping the ViewModel.
2. ViewModel: `class <Name>ViewModel(...) : androidx.lifecycle.ViewModel()`, state is an immutable `StateFlow<...>` (`data class`), events are functions. Created in the graph: `viewModel { <Name>ViewModel(deps) }`.
3. Read state with `collectAsStateWithLifecycle()`.
4. Title: `DetailScaffold(title = Routes.titleOf(Routes.X))` — the back button comes from `LocalOnBack` provided by the shell.
5. Navigation: `deps.navigator.go(Routes.Y)` / `back()` / `openFinance(tab)`. Snackbar: `LocalPemaSnackbar.current.showSnackbar(...)`.
6. Hardware: `deps.platform` / `LocalPlatformServices.current`. Tests use `FakePlatformServices`.

## Visuals: follow the canvas
- Only use tokens from `PemaColors` and text styles `PemaType.*` (which include Be Vietnam Pro). Never set colors/font sizes that differ from the canvas.
- Icons: `PemaIcon("material_name")` — outlined glyph `PemaIcon("x")`, filled glyph `PemaIcon("x", filled = true)`.
- Feature-specific blocks (order card, A5 slip, CSKH row, finance card…) are built in the feature module from that block's CSS in the canvas.
- **Required image comparison loop**: in the module's `jvmTest`, call `shotVsCanvas("F4") { QuickOrderScreen(state, …) }` → `build/shots/F4-vs.png` = canvas image (left) | Compose (right). Look at it and fix until it matches. Reference images are rendered from the canvas into `pema-kmp/design-ref/` by the Gradle task `canvasRefs` before every `jvmTest` (skipped when the canvas is unchanged); re-render manually: `.\gradlew.bat canvasRefs` or `node .claude\skills\pema-canvas-to-kmp-compose\scripts\canvas-shots.cjs --force`. `PEMA_REF_DIR` overrides the folder.

## Web-only screens (canvas I/J/K)
- Logic follows `prototype/` (web); data comes from `deps.clinicStore` (`shared/clinic`). New commands are `ClinicStore.xxx()` extensions in `shared/clinic/<Feature>Commands.kt` using `transact` (errors = `ClinicError` with the web's Vietnamese message).
- Permissions: `Session.allows` follows `staff-context.js` (`pages` + `capabilities`); buttons that need a capability (clinical/billing/config) are hidden via `session.staffContext().can(...)`.
- Don't change how A–H screens look when adding entry points: add items at the end of the screen, or an optional callback parameter (default `null` = hidden) so the A–H shots stay the same.
- Route titles must be unique in `Routes.titles` (used by `idOf`); if an app bar needs the same name as another screen, declare it in `appBarTitles` and use `Routes.appBarTitleOf`.

## Mobile-first & performance
- Design for portrait phones 360–412dp; touch targets ≥ 48dp; `LazyColumn`/`LazyRow` for lists, with `key`.
- Screens whose content can grow past one screen (lists of patients, tiles, rows) use a `LazyColumn` body (`LazyDetailScaffold`, or a `LazyListScope.xxxItems(...)` builder like `patientSearchItems`) — not `Column` + `verticalScroll` + `forEach`, which composes every row on each open/tab switch. Filter/sort in `remember(inputs)` or the ViewModel, not on every recomposition.
- `PemaIcon` draws its glyph from a `TextMeasurer` cache shared through `PemaTheme` (`LocalPemaIconMeasurer`); don't replace it with a `BasicText` per icon.
- Judge speed on a **release** build (`Build Variants` → `release`, already signed with the debug key): debug builds of Compose are 3–6× slower (measured: owner "Hồ sơ" tab 269 ms debug vs 67 ms release on the emulator). Measure with `adb shell dumpsys gfxinfo com.pema.clinic.kmp framestats`.
- State is `@Immutable`/`data class`, lists are immutable `List`s; avoid heavy work in composables (use `remember`/`derivedStateOf` or the ViewModel).
- Never block the main thread; IO through `suspend` + `Dispatchers.Default`/Ktor.
- Vietnamese UI text stays exactly as in the canvas/specs. **Files must be saved as UTF-8** (don't use the default PowerShell `Set-Content`/`Out-File` — use the create/edit tools or `[IO.File]::WriteAllText(p, t, (New-Object Text.UTF8Encoding($false)))`).

## Compose gotchas seen on devices (JVM shots don't catch them)
- App stores live in `AppStores` (one `AppContainer` per process); `FeatureDeps` is rebuilt for each activity with the new navigator/platform. Never create stores in `remember` of the root composable — rotating the phone would reset the whole session.
- The workspace (`Session`: role, selected patient) is saved with the back stack by `RestoreSessionAfterProcessDeath` in `App.kt` and restored before `NavHost` composes, so a screen restored after process death keeps its role.
- Photos/camera: call `deps.platform.camera.capture()` / `pick()` in a coroutine, catch `HardwareFailure` (Vietnamese message) to show a snackbar; `null` = the user cancelled. Screens with photos must collect `camera.recoveredPhotos()` (photos that arrive after the activity was recreated) and delete unsaved photos with `OnScreenCleared(key) { camera.discard(...) }` — not `DisposableEffect` (it also runs on rotation). Keep the photo path in `rememberSaveable`. When a photo is sent/saved into the data, call `camera.markSaved(path)`: it stops being a draft and is cleaned up on the next process start (demo data only lives in memory).
- Testing the camera on the emulator: the system camera app shows a virtual scene; simulate Android killing the app during capture with `adb shell settings put global always_finish_activities 1` (remember to set it back to `0`). On a real phone, `adb shell am kill com.pema.clinic.kmp` while the camera is open kills the process for real.
- FABs in `DetailScaffold`/`LazyDetailScaffold` are already padded for the system navigation bar; don't place a FAB outside the `floatingActionButton` slot (the navigation bar would cover it).
- A "Resizable" emulator after many `am force-stop`s can keep a stale input focus → the Back key causes the ANR "does not have a focused window" after closing a sheet. That is emulator state (restarting the emulator fixes it), not an app bug — check `dumpsys input` FocusRequests before changing code.
- Snackbar shown before/after `back()` (save → go back): use `rememberPemaMessenger().show(msg)` (root scope in `App.kt`). The screen's `rememberCoroutineScope()` is cancelled on pop → the message is lost.
- Tab/filter/search state of a screen covered by another route: `rememberSaveable` (NavHost drops `remember` of covered screens). Types that can't go into a Bundle (data classes, nested enums) need a `listSaver`/`mapSaver`, otherwise Android crashes when navigating.
- Don't nest `verticalScroll` inside `PemaBottomSheet`/`ModalBottomSheet` (crash); only one scrolling layer.
- Keyboard: `PemaScaffold` already pads for the IME and the manifest uses `adjustResize`; don't add `imePadding()` again.
- `composeResources` in library modules need `androidResources.enable = true` (already enabled in the convention plugin).

## Gradle commands (PowerShell, Windows)
```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'; cd E:\Desktop\cnbphongkham\pema-kmp
.\gradlew.bat :feature:<x>:compileAndroidMain --console=plain -q     # compile one feature
.\gradlew.bat :feature:<x>:jvmTest --console=plain -q                # run commonTest on the JVM
.\gradlew.bat :shared:jvmTest --tests "com.pema.clinic.shared.<area>*" --console=plain -q
.\gradlew.bat :androidApp:assembleDebug --console=plain -q           # APK (integration)
.\gradlew.bat :composeApp:compileKotlinIosArm64 "-Pkotlin.native.enableKlibsCrossCompilation=true"   # type-check iosMain on Windows
```
- Several agents in parallel: on "Timeout waiting to lock" / "Gradle daemon busy" → wait 30–60 s and rerun.
- iOS: Windows can compile the iOS klibs (command above) but cannot link the app; the app is built by `.github/workflows/ios-kmp.yml` on GitHub Actions (see `iosApp/README.md`).
- Device: `E:\apdata\platform-tools\adb.exe`, phone `08031a5f0407`, package `com.pema.clinic.kmp`.

## Available libraries (commonMain)
Compose 1.12.1 (runtime/foundation/material3 1.9.0/ui/components-resources), navigation-compose 2.9.2, lifecycle-viewmodel-compose 2.10.0, coroutines, kotlinx-serialization-json, kotlinx-datetime (use `kotlin.time.Clock`/`Instant` + `@OptIn(ExperimentalTime::class)`), Ktor 3.6 (+ `ktor-client-mock` for tests). Tests: `kotlin.test`.
