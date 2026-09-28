package com.pema.clinic.core.ui.widgets

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.indication
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ripple
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.shadow.Shadow
import androidx.compose.ui.draw.dropShadow
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.DpOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType

/**
 * Destination of [PemaBottomNav]. [icon] is the outlined glyph, [activeIcon]
 * the filled glyph shown when selected (Flutter `getActiveIcon`, e.g.
 * `route` → `alt_route`). [badge] shows the red M3 badge (e.g. unread "1").
 */
@Immutable
data class PemaNavItem(val label: String, val icon: String, val activeIcon: String = icon, val badge: String? = null)

private val EaseOutCubic = CubicBezierEasing(0.33f, 1f, 0.68f, 1f)
private val EaseOutBack = CubicBezierEasing(0.175f, 0.885f, 0.32f, 1.275f)

/**
 * Flutter `PemaModernBottomNav` · canvas `hasNav`: white dock, 20 top radius,
 * #E2E8F0 top border, layered blue shadow, 66 high, 64×32 capsule
 * (#EAF4FC / #D0E6F9) behind the filled blue icon (scale 1.12), 11.5 labels,
 * sliding 36×3 accent bar. Adds the system navigation-bar inset below.
 */
@Composable
fun PemaBottomNav(
    items: List<PemaNavItem>,
    selectedIndex: Int,
    onSelect: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val dock = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)
    Box(
        modifier
            .fillMaxWidth()
            .dropShadow(dock, Shadow(radius = 20.dp, color = Color(0x0E0B4F94), offset = DpOffset(0.dp, (-6).dp)))
            .dropShadow(dock, Shadow(radius = 6.dp, color = Color(0x05000000), offset = DpOffset(0.dp, (-1).dp)))
            .clip(dock)
            .background(Color.White)
            .border(1.dp, PemaColors.NavBorder, dock)
            .windowInsetsPadding(pemaNavigationBars),
        contentAlignment = Alignment.TopCenter,
    ) {
        BoxWithConstraints(Modifier.widthIn(max = 720.dp).fillMaxWidth().height(66.dp)) {
            val count = items.size.coerceAtLeast(1)
            val tab = maxWidth / count
            val barLeft by animateDpAsState(
                (tab * selectedIndex + (tab - 36.dp) / 2).coerceIn(0.dp, maxWidth - 36.dp),
                tween(300, easing = EaseOutCubic),
            )
            Row(Modifier.fillMaxWidth().fillMaxHeight()) {
                items.forEachIndexed { i, item ->
                    NavDestination(item, selected = i == selectedIndex, onClick = { onSelect(i) }, modifier = Modifier.weight(1f))
                }
            }
            if (items.isNotEmpty()) {
                Box(
                    Modifier
                        .offset(x = barLeft)
                        .size(36.dp, 3.dp)
                        .dropShadow(RoundedCornerShape(2.dp), Shadow(radius = 4.dp, color = Color(0x550B4F94), offset = DpOffset(0.dp, 1.dp)))
                        .background(PemaColors.Blue, RoundedCornerShape(2.dp)),
                )
            }
        }
    }
}

@Composable
private fun NavDestination(item: PemaNavItem, selected: Boolean, onClick: () -> Unit, modifier: Modifier) {
    val source = remember { MutableInteractionSource() }
    val scale by animateFloatAsState(if (selected) 1.12f else 1f, tween(260, easing = EaseOutBack))
    val capsuleAlpha by animateFloatAsState(if (selected) 1f else 0f, tween(300))
    Column(
        modifier
            .fillMaxHeight()
            .semantics { this.selected = selected }
            .clickable(interactionSource = source, indication = null, role = Role.Tab, onClick = onClick),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp, Alignment.CenterVertically),
    ) {
        val capsule = RoundedCornerShape(16.dp)
        Box(Modifier.size(64.dp, 32.dp), contentAlignment = Alignment.Center) {
            Box(
                Modifier
                    .matchParentSizeCompat()
                    .clip(capsule)
                    .background(PemaColors.NavCapsule.copy(alpha = capsuleAlpha))
                    .border(1.dp, PemaColors.NavCapsuleBorder.copy(alpha = capsuleAlpha), capsule)
                    .indication(source, ripple()),
            )
            if (selected) {
                PemaIcon(item.activeIcon, Modifier.scale(scale), size = 24.dp, color = PemaColors.Blue, filled = true)
            } else {
                PemaIcon(item.icon, size = 23.dp, color = PemaColors.NavIdle)
            }
            if (item.badge != null) PemaBadge(item.badge, Modifier.align(Alignment.TopStart).padding(start = 34.dp))
        }
        Text(
            item.label,
            style = PemaType.of(
                11.5f,
                if (selected) FontWeight.W600 else FontWeight.W500,
                if (selected) PemaColors.Blue else PemaColors.NavIdle,
                height = 16f / 11.5f,
                letterSpacing = (-0.1).sp,
            ),
            maxLines = 1,
            softWrap = false,
        )
    }
}

private fun Modifier.matchParentSizeCompat() = this.fillMaxWidth().fillMaxHeight()

/** M3 large `Badge`: 16 high, #BA1A1A, white 11/500 label. */
@Composable
fun PemaBadge(text: String, modifier: Modifier = Modifier) {
    Box(
        modifier
            .heightIn(min = 16.dp)
            .widthIn(min = 16.dp)
            .background(PemaColors.Error, RoundedCornerShape(8.dp))
            .padding(horizontal = 4.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, style = PemaType.of(11f, FontWeight.W500, Color.White, height = 16f / 11f), maxLines = 1)
    }
}
