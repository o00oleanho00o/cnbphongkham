package com.pema.clinic.core.ui.widgets

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType

/*
 * Canvas blocks used by the web-only screens (I/J/K): `fc(...)` card with
 * `ftitle`, `fl`, `txt`, `fb` (text buttons) and `ff` (filled button),
 * standalone `txt(...)` and `careRow(...)`.
 */

/** Canvas `fc(...)`: white card, radius 18, border #D9E5EE, padding 18, 16dp below. */
@Composable
fun PemaInfoCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val shape = RoundedCornerShape(18.dp)
    Column(
        modifier
            .fillMaxWidth()
            .padding(bottom = 16.dp)
            .background(Color.White, shape)
            .border(1.dp, PemaColors.FieldBorderDefault, shape)
            .padding(18.dp),
        horizontalAlignment = Alignment.Start,
        content = content,
    )
}

/** Canvas `ftitle(...)`: 18sp w700, 12dp below. Used inside [PemaInfoCard] and standalone. */
@Composable
fun PemaCardTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, style = PemaType.financeTitle, modifier = modifier.padding(bottom = 12.dp))
}

/** Canvas `fl(label, value)`: label fills the row, value w600; 8dp vertical padding. */
@Composable
fun PemaCardLine(label: String, value: String, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Text(label, style = PemaType.body, modifier = Modifier.weight(1f))
        Text(value, style = PemaType.bodyStrong, maxLines = 1)
    }
}

/** Canvas `fb(...)`: a wrap of 40dp text buttons (blue 14sp w500). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PemaCardTextButtons(vararg buttons: Pair<String, () -> Unit>, modifier: Modifier = Modifier) {
    FlowRow(modifier, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        buttons.forEach { (text, onClick) ->
            Box(
                Modifier
                    .height(40.dp)
                    .clip(CircleShape)
                    .clickable(onClick = onClick)
                    .padding(horizontal = 12.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(text, style = PemaType.of(14f, FontWeight.W500, PemaColors.Blue))
            }
        }
    }
}

/** Canvas `ff(text)`: 52dp filled button that wraps its label (not full width), radius 14. */
@Composable
fun PemaCardFilledButton(text: String, onClick: (() -> Unit)?, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(14.dp)
    val enabled = onClick != null
    Box(
        modifier
            .heightIn(min = 52.dp)
            .clip(shape)
            .background(if (enabled) PemaColors.Blue else PemaColors.Disabled, shape)
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(horizontal = 24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, style = PemaType.of(14f, FontWeight.W500, if (enabled) Color.White else PemaColors.DisabledContent))
    }
}

/**
 * Canvas `txt(text, {s, c, w})`: plain text, line height 1.5, keeps line breaks.
 * Defaults match the canvas (14sp, ink, w400).
 */
@Composable
fun PemaText(
    text: String,
    modifier: Modifier = Modifier,
    size: Float = 14f,
    color: Color = PemaColors.Ink,
    weight: FontWeight = FontWeight.W400,
    maxLines: Int = Int.MAX_VALUE,
) {
    Text(
        text,
        style = PemaType.of(size, weight, color, height = 1.5f),
        modifier = modifier,
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
    )
}

/** Canvas `careRow(...)`: 40dp initials avatar, name, blue group line, muted meta, chevron. */
@Composable
fun PemaCareRow(
    initials: String,
    name: String,
    group: String,
    meta: String,
    onClick: (() -> Unit)?,
    modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(18.dp)
    Row(
        modifier
            .padding(bottom = 10.dp)
            .fillMaxWidth()
            .clip(shape)
            .background(PemaColors.White)
            .border(1.dp, PemaColors.Line, shape)
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(14.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(40.dp).background(PemaColors.CareAvatar, CircleShape), contentAlignment = Alignment.Center) {
            Text(initials, style = PemaType.of(13f, FontWeight.W600, PemaColors.Blue))
        }
        Column(Modifier.weight(1f)) {
            Text(name, style = PemaType.of(14f, FontWeight.W600, PemaColors.Ink, height = 1.4f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                group,
                style = PemaType.of(12f, color = PemaColors.Blue, height = 1.4f),
                modifier = Modifier.padding(top = 5.dp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                meta,
                style = PemaType.of(11f, color = PemaColors.Muted, height = 1.4f),
                modifier = Modifier.padding(top = 7.dp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        PemaIcon("chevron_right", size = 20.dp, color = PemaColors.Muted, modifier = Modifier.padding(top = 4.dp))
    }
}
