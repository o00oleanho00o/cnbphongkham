package com.pema.clinic.core.ui.widgets

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.wrapContentSize
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType

/*
 * 1:1 port of flutter-template/lib/core/widgets/pema_blocks.dart. Every size,
 * colour and spacing is the canvas CSS of the matching block
 * (`Pema App redesign canvas/Pema App.dc.html`, `<sc-if value="{{ b.<name> }}">`).
 * Blocks are meant to be stacked in a DetailScaffold / Workspace column with
 * horizontal padding 20; they fill the width like Flutter ListView children.
 */

/** Canvas `heading` · Flutter `heading(title, sub)`. */
@Composable
fun PemaHeading(title: String, sub: String, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(bottom = 20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, style = PemaType.heading)
        Text(sub, style = PemaType.sub13)
    }
}

/** Canvas `h2`: 26/700 ink title + 13 muted subtitle (patient Care screens). */
@Composable
fun PemaH2(title: String, sub: String, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(bottom = 20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, style = PemaType.h2)
        Text(sub, style = PemaType.sub13)
    }
}

/** Canvas `section` · Flutter `section(title)`. */
@Composable
fun PemaSection(title: String, modifier: Modifier = Modifier) {
    Text(title, style = PemaType.section, modifier = modifier.fillMaxWidth().padding(top = 24.dp, bottom = 12.dp))
}

/** Canvas `hero` · Flutter `hero(title, sub, icon)`. */
@Composable
fun PemaHero(title: String, sub: String, icon: String, modifier: Modifier = Modifier, iconFilled: Boolean = false) {
    Box(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(
                Brush.linearGradient(
                    listOf(PemaColors.Navy, PemaColors.Blue),
                    start = Offset.Zero,
                    end = Offset(Float.POSITIVE_INFINITY, Float.POSITIVE_INFINITY),
                ),
            ),
    ) {
        Box(Modifier.matchParentSize()) {
            PemaIcon(
                icon,
                Modifier.align(Alignment.TopEnd).wrapContentSize(Alignment.TopEnd, unbounded = true).offset(x = 20.dp, y = (-22).dp),
                size = 170.dp,
                color = Color.White.copy(alpha = 0.09f),
                filled = iconFilled,
            )
        }
        Column(Modifier.padding(24.dp)) {
            Text("PEMA • CHĂM SÓC LIÊN TỤC", style = PemaType.heroKicker)
            Spacer(Modifier.height(16.dp))
            Text(title, style = PemaType.heroTitle)
            Spacer(Modifier.height(16.dp))
            Text(sub, style = PemaType.heroSub)
        }
    }
}

/** Canvas `metrics` item · Flutter `metric(value, label)` (an `Expanded`). */
@Composable
fun RowScope.PemaMetric(value: String, label: String, modifier: Modifier = Modifier) {
    Column(modifier.weight(1f).fillMaxHeight().background(Color.White, RoundedCornerShape(18.dp)).padding(18.dp)) {
        Text(value, style = PemaType.metricValue)
        Text(label, style = PemaType.caption)
    }
}

/** Canvas `metrics`: a row of [PemaMetric] with 12dp gaps; cards stretch to the tallest (CSS flex). */
@Composable
fun PemaMetrics(vararg items: Pair<String, String>, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth().height(androidx.compose.foundation.layout.IntrinsicSize.Min),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        items.forEach { (value, label) -> PemaMetric(value, label) }
    }
}

@Immutable
data class PemaAction(val label: String, val icon: String, val onClick: () -> Unit)

/** Canvas `actions` · Workspace "Bắt đầu nhanh" row (`action()` in workspace_screen.dart). */
@Composable
fun PemaActions(items: List<PemaAction>, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth()) {
        items.forEach { item ->
            Box(Modifier.weight(1f).padding(4.dp)) {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(18.dp))
                        .background(Color.White)
                        .clickable(onClick = item.onClick)
                        .padding(vertical = 16.dp, horizontal = 4.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(9.dp),
                ) {
                    PemaIcon(item.icon, size = 24.dp, color = PemaColors.Blue)
                    Text(item.label, style = PemaType.of(12f, androidx.compose.ui.text.font.FontWeight.W600), textAlign = TextAlign.Center)
                }
            }
        }
    }
}

/**
 * Canvas `tile` · Flutter `tile(title, sub, icon, tap)`: white card, 18 radius,
 * #E3ECF3 border, avatar #E8F4FB with blue icon, chevron only when tappable.
 */
@Composable
fun PemaTile(
    title: String,
    sub: String,
    icon: String,
    onClick: (() -> Unit)?,
    modifier: Modifier = Modifier,
    iconFilled: Boolean = false,
) {
    val shape = RoundedCornerShape(18.dp)
    Row(
        modifier
            .padding(bottom = 10.dp)
            .fillMaxWidth()
            .heightIn(min = 74.dp)
            .clip(shape)
            .background(Color.White)
            .border(1.dp, PemaColors.TileBorder, shape)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 16.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Box(Modifier.size(40.dp).background(PemaColors.Tint, CircleShape), contentAlignment = Alignment.Center) {
            PemaIcon(icon, size = 21.dp, color = PemaColors.Blue, filled = iconFilled)
        }
        Column(Modifier.weight(1f)) {
            Text(title, style = PemaType.tileTitle)
            Text(sub, style = PemaType.tileSub)
        }
        if (onClick != null) PemaIcon("chevron_right", size = 18.dp, color = PemaColors.Muted)
    }
}

/** Canvas `notice` · Flutter `notice(text)`. */
@Composable
fun PemaNotice(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        style = PemaType.notice,
        modifier = modifier
            .padding(bottom = 16.dp)
            .fillMaxWidth()
            .background(PemaColors.Tint, RoundedCornerShape(14.dp))
            .padding(16.dp),
    )
}

/** Canvas `primary` · Flutter `primary(text, tap)`: full-width FilledButton, 8dp vertical padding. */
@Composable
fun PemaPrimary(text: String, onClick: (() -> Unit)?, modifier: Modifier = Modifier) {
    PemaFilledButton(text, onClick = onClick ?: {}, enabled = onClick != null, modifier = modifier.padding(vertical = 8.dp).fillMaxWidth())
}

/** Canvas `empty`: white 18-radius card, blue `task_alt`, centred muted text. */
@Composable
fun PemaEmpty(text: String, modifier: Modifier = Modifier, icon: String = "task_alt") {
    Column(
        modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(18.dp)).padding(28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PemaIcon(icon, size = 28.dp, color = PemaColors.Blue)
        Text(text, style = PemaType.body.copy(color = PemaColors.Muted), textAlign = TextAlign.Center)
    }
}
