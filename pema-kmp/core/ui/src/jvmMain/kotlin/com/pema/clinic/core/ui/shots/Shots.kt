package com.pema.clinic.core.ui.shots

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import com.pema.clinic.core.ui.widgets.LocalSystemInsetsOverride
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.ImageComposeScene
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.use
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaTheme
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.PemaIcon
import org.jetbrains.skia.EncodedImageFormat
import java.awt.Color
import java.awt.image.BufferedImage
import java.io.File
import javax.imageio.ImageIO

/** Canvas phone screen size (dp) – `Pema App.dc.html` frames are 390×844. */
const val CANVAS_WIDTH_DP = 390
const val CANVAS_HEIGHT_DP = 844

/**
 * Renders [content] inside [PemaTheme] and the canvas phone frame (47dp status
 * bar "9:41", home indicator) to a PNG at [scale]× – the same size as the
 * canvas reference shots (`files/ref/<ID>.png`, 780×1690). Use from jvmTest:
 *
 * ```
 * @Test fun a1() { shotVsCanvas("A1") { WorkspaceScreen(...) } }
 * ```
 *
 * Several frames are rendered so fonts load and animations settle.
 */
@OptIn(ExperimentalComposeUiApi::class)
fun renderScreen(
    out: File,
    widthDp: Int = CANVAS_WIDTH_DP,
    heightDp: Int = CANVAS_HEIGHT_DP,
    scale: Float = 2f,
    frame: Boolean = true,
    content: @Composable () -> Unit,
): File {
    out.absoluteFile.parentFile.mkdirs()
    ImageComposeScene(
        width = (widthDp * scale).toInt(),
        height = (heightDp * scale).toInt(),
        density = Density(scale),
    ) {
        PemaTheme {
            if (frame) CanvasFrame(content) else Box(Modifier.fillMaxSize().background(PemaColors.Paper)) { content() }
        }
    }.use { scene ->
        var image = scene.render(0L)
        for (i in 1..12) image = scene.render(i * 250_000_000L)
        val png = image.encodeToData(EncodedImageFormat.PNG) ?: error("PNG encode failed")
        out.writeBytes(png.bytes)
    }
    return out
}

@Composable
private fun CanvasFrame(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize().background(PemaColors.Paper)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().height(47.dp).padding(start = 34.dp, end = 26.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("9:41", style = PemaType.of(15f, FontWeight.W600, PemaColors.Ink))
                Row(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.CenterVertically) {
                    PemaIcon("signal_cellular_alt", size = 17.dp, color = PemaColors.Ink, filled = true)
                    PemaIcon("wifi", size = 17.dp, color = PemaColors.Ink, filled = true)
                    PemaIcon("battery_full", Modifier.rotate(90f), size = 20.dp, color = PemaColors.Ink, filled = true)
                }
            }
            Box(Modifier.weight(1f).fillMaxWidth()) {
                CompositionLocalProvider(LocalSystemInsetsOverride provides WindowInsets(bottom = 34.dp)) { content() }
            }
        }
        Box(
            Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 8.dp)
                .size(134.dp, 5.dp)
                .background(PemaColors.Ink, RoundedCornerShape(3.dp)),
        )
    }
}

/**
 * Writes `reference | ours` side by side so one image shows both – view it to
 * compare a screen with its canvas reference.
 */
fun sideBySide(reference: File, ours: File, out: File): File {
    val a = ImageIO.read(reference)
    val b = ImageIO.read(ours)
    val h = maxOf(a.height, b.height)
    val gap = 24
    val img = BufferedImage(a.width + gap + b.width, h, BufferedImage.TYPE_INT_RGB)
    val g = img.createGraphics()
    g.color = Color(0xE6, 0xED, 0xF3)
    g.fillRect(0, 0, img.width, img.height)
    g.drawImage(a, 0, 0, null)
    g.drawImage(b, a.width + gap, 0, null)
    g.dispose()
    out.absoluteFile.parentFile.mkdirs()
    ImageIO.write(img, "png", out)
    return out
}

/**
 * Canvas reference shots, rendered by the root Gradle task `canvasRefs`
 * (`.claude/skills/pema-canvas-to-kmp-compose/scripts/canvas-shots.cjs`) into `pema-kmp/design-ref`.
 * jvmTest passes that folder as `-Dpema.refDir`; `PEMA_REF_DIR` overrides it.
 */
val canvasRefDir: File
    get() = File(
        System.getProperty("pema.refDir")
            ?: System.getenv("PEMA_REF_DIR")
            ?: "../../design-ref",
    )

/**
 * Renders [content] to `build/shots/<id>.png` and, when the canvas reference
 * `<refDir>/<id>.png` exists, writes `build/shots/<id>-vs.png` (reference | ours).
 */
fun shotVsCanvas(id: String, dir: File = File("build/shots"), content: @Composable () -> Unit): File {
    val ours = renderScreen(File(dir, "$id.png"), content = content)
    val ref = File(canvasRefDir, "$id.png")
    if (!ref.exists()) println("shotVsCanvas: no canvas reference ${ref.path} – run `gradlew canvasRefs`.")
    return if (ref.exists()) sideBySide(ref, ours, File(dir, "$id-vs.png")) else ours
}
