package com.pema.clinic.core.ui.widgets

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.LocalPemaFonts
import kotlin.math.roundToInt

/**
 * Material Icons glyph by ligature name – the same font Flutter's `Icons.*` use.
 *
 * Name mapping from Flutter: `Icons.foo_outlined` / `Icons.foo_outline` → `PemaIcon("foo")`,
 * `Icons.foo` (filled) → `PemaIcon("foo", filled = true)`. Canvas icons are
 * the same names (`font-variation-settings:'FILL' 1` → `filled = true`).
 * A wrong name renders its letters, so check screenshots.
 */
@Composable
fun PemaIcon(
    name: String,
    modifier: Modifier = Modifier,
    size: Dp = 24.dp,
    color: Color = LocalContentColor.current,
    filled: Boolean = false,
    contentDescription: String? = null,
) {
    val fonts = LocalPemaFonts.current
    val measurer = LocalPemaIconMeasurer.current ?: rememberTextMeasurer()
    val family = if (filled) fonts.iconsFilled else fonts.iconsOutlined
    val semantics = if (contentDescription != null) {
        Modifier.clearAndSetSemantics { this.contentDescription = contentDescription; role = Role.Image }
    } else {
        Modifier.clearAndSetSemantics { }
    }
    // Drawn from a layout cached by the shared measurer (not a BasicText node per icon): a list of
    // tiles lays out each glyph once, e.g. one "chevron_right" for every row.
    Spacer(
        modifier.then(semantics).size(size).drawWithCache {
            val sp = size.toSp()
            val layout = measurer.measure(
                text = name,
                style = TextStyle(
                    fontFamily = family,
                    fontSize = sp,
                    lineHeight = sp,
                    textAlign = TextAlign.Center,
                    lineHeightStyle = IconLineHeight,
                ),
                maxLines = 1,
                softWrap = false,
                constraints = Constraints(maxWidth = this.size.width.roundToInt(), maxHeight = this.size.height.roundToInt()),
            )
            val topLeft = Offset(
                ((this.size.width - layout.size.width) / 2f).roundToInt().toFloat(),
                ((this.size.height - layout.size.height) / 2f).roundToInt().toFloat(),
            )
            onDrawBehind { drawText(layout, color = color, topLeft = topLeft) }
        },
    )
}

private val IconLineHeight = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.Both)

/** Shared by every [PemaIcon] (provided by `PemaTheme`) so glyph layouts are cached app-wide. */
val LocalPemaIconMeasurer = staticCompositionLocalOf<TextMeasurer?> { null }
