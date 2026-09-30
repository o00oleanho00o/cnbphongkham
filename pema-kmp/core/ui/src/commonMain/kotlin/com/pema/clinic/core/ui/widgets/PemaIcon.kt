package com.pema.clinic.core.ui.widgets

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.LocalPemaFonts

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
    val sp = with(LocalDensity.current) { size.toSp() }
    val semantics = if (contentDescription != null) {
        Modifier.clearAndSetSemantics { this.contentDescription = contentDescription; role = Role.Image }
    } else {
        Modifier.clearAndSetSemantics { }
    }
    Box(modifier.then(semantics).size(size), contentAlignment = Alignment.Center) {
        BasicText(
            text = name,
            style = TextStyle(
                fontFamily = if (filled) fonts.iconsFilled else fonts.iconsOutlined,
                fontSize = sp,
                lineHeight = sp,
                color = color,
                textAlign = TextAlign.Center,
                lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.Both),
            ),
            maxLines = 1,
            softWrap = false,
        )
    }
}
