package com.pema.clinic.core.ui.widgets

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.SnackbarData
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.generated.resources.Res
import com.pema.clinic.core.ui.generated.resources.pema_logo
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import org.jetbrains.compose.resources.painterResource

/**
 * Flutter `showModalBottomSheet(showDragHandle: true, isScrollControlled: true,
 * maxHeight: 85%)` · canvas `hasSheet`: white, 28 top radius, 32×4 handle in
 * a 48 band, black54 scrim. [content] scrolls; pad it like the Flutter sheet.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PemaBottomSheet(onDismiss: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val maxHeight = with(LocalDensity.current) { (LocalWindowInfo.current.containerSize.height * 0.85f).toDp() }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = state,
        containerColor = Color.White,
        contentColor = PemaColors.Ink,
        scrimColor = PemaColors.Black54,
        tonalElevation = 0.dp,
        shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp),
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .heightIn(max = maxHeight)
                .verticalScroll(rememberScrollState())
                .windowInsetsPadding(pemaNavigationBars),
            content = content,
        )
    }
}

/**
 * Flutter `ListTile` (sheet rows, settings rows): min 56, content padding
 * 16/24, leading icon 24 #43474E, title bodyLarge 16 #1A1C20, optional
 * subtitle and trailing. Canvas sheet `rows`.
 */
@Composable
fun PemaListRow(
    title: String,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    leadingIcon: String? = null,
    leadingColor: Color = PemaColors.OnSurfaceVariant,
    leadingSize: Dp = 24.dp,
    leadingFilled: Boolean = false,
    subtitle: String? = null,
    titleStyle: TextStyle = PemaType.input,
    contentPadding: PaddingValues = PaddingValues(start = 16.dp, end = 24.dp),
    trailing: (@Composable RowScope.() -> Unit)? = null,
) {
    Row(
        modifier
            .fillMaxWidth()
            .heightIn(min = if (subtitle == null) 56.dp else 72.dp)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(contentPadding)
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        if (leadingIcon != null) PemaIcon(leadingIcon, size = leadingSize, color = leadingColor, filled = leadingFilled)
        Column(Modifier.weight(1f)) {
            Text(title, style = titleStyle)
            if (subtitle != null) Text(subtitle, style = PemaType.of(14f, color = PemaColors.OnSurfaceVariant, height = 20f / 14f))
        }
        trailing?.invoke(this)
    }
}

/** Flutter M3 fixed `SnackBar` · canvas `hasSnack`: full width, #2F3036, action #A6C8FF. */
@Composable
fun PemaSnackbar(data: SnackbarData) {
    Surface(Modifier.fillMaxWidth(), shape = RectangleShape, color = PemaColors.InverseSurface, contentColor = PemaColors.InverseOnSurface, shadowElevation = 6.dp) {
        Row(Modifier.heightIn(min = 48.dp).padding(start = 16.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(
                data.visuals.message,
                style = PemaType.of(14f, color = PemaColors.InverseOnSurface, height = 20f / 14f),
                modifier = Modifier.weight(1f).padding(vertical = 14.dp),
            )
            val action = data.visuals.actionLabel
            if (action != null) {
                TextButton(onClick = { data.performAction() }, colors = ButtonDefaults.textButtonColors(contentColor = PemaColors.InversePrimary)) {
                    Text(action, style = PemaType.label)
                }
            }
        }
    }
}

/**
 * M3 `AlertDialog` as Flutter renders it (surfaceContainerHigh, radius 28,
 * headlineSmall title). Confirm is a Pema FilledButton, dismiss a TextButton –
 * canvas `hasDialog`.
 */
@Composable
fun PemaDialog(
    title: String,
    onDismiss: () -> Unit,
    confirmText: String,
    onConfirm: () -> Unit,
    confirmEnabled: Boolean = true,
    dismissText: String? = "Quay lại",
    content: (@Composable () -> Unit)? = null,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title, style = androidx.compose.material3.MaterialTheme.typography.headlineSmall.copy(color = PemaColors.OnSurface)) },
        text = content,
        containerColor = PemaColors.SurfaceContainerHigh,
        shape = RoundedCornerShape(28.dp),
        confirmButton = { PemaFilledButton(confirmText, onClick = onConfirm, enabled = confirmEnabled) },
        dismissButton = dismissText?.let { { PemaTextButton(it, onClick = onDismiss) } },
    )
}

/** Flutter `FloatingActionButton.extended` · canvas `hasFab` (primaryContainer, radius 16, h56). */
@Composable
fun PemaExtendedFab(text: String, onClick: () -> Unit, icon: String = "add", modifier: Modifier = Modifier) {
    ExtendedFloatingActionButton(
        onClick = onClick,
        modifier = modifier,
        containerColor = PemaColors.PrimaryContainer,
        contentColor = PemaColors.OnPrimaryContainer,
        icon = { PemaIcon(icon, size = 24.dp) },
        text = { Text(text, style = PemaType.label) },
    )
}

/**
 * Flutter `WeekStrip` (schedule) · canvas `week`: T2…CN, dates 21+i, index 1 selected.
 * Pass [days] (weekday label to date label), [selected] and [onSelect] for a working day picker
 * (web schedule); the default is Flutter's static strip.
 */
@Composable
fun WeekStrip(
    modifier: Modifier = Modifier,
    days: List<Pair<String, String>> = listOf("T2", "T3", "T4", "T5", "T6", "T7", "CN").mapIndexed { i, d -> d to "${21 + i}" },
    selected: Int = 1,
    onSelect: ((Int) -> Unit)? = null,
) {
    Row(modifier.fillMaxWidth().padding(bottom = 20.dp)) {
        days.forEachIndexed { i, (day, date) ->
            val on = i == selected
            Column(
                Modifier
                    .weight(1f)
                    .padding(horizontal = 2.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(if (on) PemaColors.Blue else Color.White, RoundedCornerShape(12.dp))
                    .let { if (onSelect != null) it.clickable { onSelect(i) } else it }
                    .padding(vertical = 12.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(day, style = PemaType.of(10f, color = if (on) Color.White else PemaColors.Muted))
                Spacer(Modifier.height(8.dp))
                Text(date, style = PemaType.of(14f, androidx.compose.ui.text.font.FontWeight.W700, if (on) Color.White else PemaColors.Ink))
            }
        }
    }
}

/** `assets/pema-logo.png` at Flutter's AppBar width 94. */
@Composable
fun PemaLogo(modifier: Modifier = Modifier, width: Dp = 94.dp) {
    Image(painterResource(Res.drawable.pema_logo), contentDescription = "Pema", modifier = modifier.width(width))
}

/**
 * Workspace AppBar (canvas `appMain`): logo, optional notifications bell with
 * unread badge, and the "swap_horiz <role>" TextButton that opens the
 * workspace picker.
 */
@Composable
fun PemaMainTopBar(
    roleLabel: String,
    onRoleClick: () -> Unit,
    modifier: Modifier = Modifier,
    unread: Int? = null,
    onBellClick: () -> Unit = {},
) {
    PemaTopBar(
        title = { PemaLogo() },
        modifier = modifier,
        actions = {
            if (unread != null) {
                PemaTopBarAction("notifications", onBellClick, contentDescription = "Thông báo thanh toán", badge = if (unread > 0) "$unread" else null)
            }
            PemaTextButton(roleLabel, onClick = onRoleClick, icon = "swap_horiz")
        },
    )
}

/**
 * Flutter `LocalPhoto`: captured photo from disk (decoded at display size),
 * radius 18, #E8F4FB placeholder with `broken_image`, optional black54 label.
 */
@Composable
fun LocalPhoto(path: String, modifier: Modifier = Modifier, height: Dp = 220.dp, label: String? = null) {
    val services = com.pema.clinic.core.hardware.LocalPlatformServices.current
    val px = with(LocalDensity.current) { height.roundToPx() }
    val image = androidx.compose.runtime.produceState<androidx.compose.ui.graphics.ImageBitmap?>(null, path, px) {
        value = runCatching { services.images.load(path, px) }.getOrNull()
    }
    Box(modifier.fillMaxWidth().height(height).background(PemaColors.Tint, RoundedCornerShape(18.dp)).clipRounded(18.dp)) {
        val bitmap = image.value
        if (bitmap != null) {
            Image(bitmap, contentDescription = label, modifier = Modifier.fillMaxWidth().height(height), contentScale = androidx.compose.ui.layout.ContentScale.Crop)
        } else {
            PemaIcon("broken_image", Modifier.align(Alignment.Center), color = PemaColors.Muted)
        }
        if (label != null) {
            Text(
                label,
                style = PemaType.of(11f, color = Color.White),
                modifier = Modifier
                    .align(Alignment.BottomStart)
                    .padding(8.dp)
                    .background(PemaColors.Black54, RoundedCornerShape(8.dp))
                    .padding(horizontal = 8.dp, vertical = 3.dp),
            )
        }
    }
}

private fun Modifier.clipRounded(radius: Dp) = this.clip(RoundedCornerShape(radius))
