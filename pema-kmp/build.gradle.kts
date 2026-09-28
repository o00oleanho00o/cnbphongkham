// Plugins come from build-logic (included via pluginManagement), so no versions are declared here.

/**
 * Canvas reference screenshots for `shotVsCanvas` (jvmTest): renders every screen of
 * `Pema App redesign canvas/Pema App.dc.html` into `design-ref/<ID>.png`.
 * Up to date (skipped) while the canvas and the script are unchanged; every module's jvmTest
 * depends on it. Needs Node + Playwright Chromium; if they are missing the task only warns and
 * the tests still run (without the `-vs.png` comparisons).
 */
val canvasRefs by tasks.registering(Exec::class) {
    group = "verification"
    description = "Render design canvas screens to design-ref/<ID>.png for shotVsCanvas."
    val repo = rootDir.parentFile
    val script = File(repo, ".claude/skills/pema-canvas-to-kmp-compose/scripts/canvas-shots.cjs")
    val canvas = File(repo, "Pema App redesign canvas/Pema App.dc.html")
    val out = layout.projectDirectory.dir("design-ref")
    inputs.files(script, canvas)
    outputs.dir(out)
    onlyIf("script and canvas present") { script.exists() && canvas.exists() }
    workingDir = repo
    commandLine("node", script.absolutePath, "--out=${out.asFile.absolutePath}")
    isIgnoreExitValue = true
    doLast {
        if (executionResult.get().exitValue != 0) {
            logger.warn("canvasRefs: could not render canvas screenshots (see output above); shots run without references.")
        }
    }
}
