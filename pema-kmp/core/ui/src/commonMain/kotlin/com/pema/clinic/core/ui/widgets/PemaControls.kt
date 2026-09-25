package com.pema.clinic.core.ui.widgets

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.InputChip
import androidx.compose.material3.InputChipDefaults
import androidx.compose.material3.LocalMinimumInteractiveComponentSize
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType

/*
 * Material widgets styled exactly as Flutter AppTheme + the canvas CSS.
 * Use these instead of raw Material3 components so every screen matches.
 */

private val Radius14 = RoundedCornerShape(14.dp)

/** Flutter `FilledButton` under AppTheme: min 48×52, radius 14, blue. Canvas `primary` / `ch.filled`. */
@Composable
fun PemaFilledButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: String? = null,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.defaultMinSize(minWidth = 48.dp, minHeight = 52.dp),
        shape = Radius14,
        colors = ButtonDefaults.buttonColors(
            containerColor = PemaColors.Blue,
            contentColor = Color.White,
            disabledContainerColor = PemaColors.Disabled,
            disabledContentColor = PemaColors.DisabledContent,
        ),
        contentPadding = PaddingValues(horizontal = 24.dp),
    ) {
        if (icon != null) {
            PemaIcon(icon, size = 18.dp)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, style = PemaType.label)
    }
}

/** Flutter `FilledButton.tonal`: secondaryContainer, same geometry as [PemaFilledButton]. */
@Composable
fun PemaTonalButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, icon: String? = null) {
    FilledTonalButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.defaultMinSize(minWidth = 48.dp, minHeight = 52.dp),
        shape = Radius14,
        contentPadding = PaddingValues(horizontal = 24.dp),
    ) {
        if (icon != null) {
            PemaIcon(icon, size = 18.dp)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, style = PemaType.label)
    }
}

/**
 * Canvas `outlined` · CSKH "Gọi" button (`OutlinedButton.styleFrom` radius 14,
 * white, #CADBE8 border): height 48, full width, blue label with 18dp icon.
 */
@Composable
fun PemaOutlinedButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, icon: String? = null, enabled: Boolean = true) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().heightIn(min = 48.dp),
        shape = Radius14,
        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color.White, contentColor = PemaColors.Blue),
        border = androidx.compose.foundation.BorderStroke(1.dp, PemaColors.FieldBorder),
        contentPadding = PaddingValues(horizontal = 16.dp),
    ) {
        if (icon != null) {
            PemaIcon(icon, size = 18.dp)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, style = PemaType.label)
    }
}

/** Canvas `pill` · default M3 `OutlinedButton(.icon)`: height 40, stadium, #74777F border. */
@Composable
fun PemaPillButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, icon: String? = null, enabled: Boolean = true) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.heightIn(min = 40.dp),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = PemaColors.Blue),
        border = androidx.compose.foundation.BorderStroke(1.dp, if (enabled) PemaColors.Outline else PemaColors.Disabled),
        contentPadding = if (icon != null) PaddingValues(start = 16.dp, end = 24.dp) else PaddingValues(horizontal = 24.dp),
    ) {
        if (icon != null) {
            PemaIcon(icon, size = 18.dp)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, style = PemaType.label)
    }
}

/** Canvas `textBtn` / `dateBtn` / AppBar role switch · M3 `TextButton(.icon)`: height 40, blue. */
@Composable
fun PemaTextButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    icon: String? = null,
    iconFilled: Boolean = false,
    enabled: Boolean = true,
    color: Color = PemaColors.Blue,
) {
    TextButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.heightIn(min = 40.dp),
        colors = ButtonDefaults.textButtonColors(contentColor = color),
        contentPadding = if (icon != null) PaddingValues(start = 12.dp, end = 16.dp) else PaddingValues(horizontal = 12.dp),
    ) {
        if (icon != null) {
            PemaIcon(icon, size = 18.dp, filled = iconFilled)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, style = PemaType.label)
    }
}

/**
 * Flutter `TextField` / `TextFormField` under AppTheme's InputDecorationTheme:
 * filled white, radius 14, #CADBE8 border, 1.5dp blue when focused, 16/24 text,
 * floating [label], optional [hint], [prefixIcon] (24dp, #43474E) and [suffix].
 * Canvas `input`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PemaTextField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    label: String? = null,
    hint: String? = null,
    prefixIcon: String? = null,
    suffix: (@Composable () -> Unit)? = null,
    minLines: Int = 1,
    maxLines: Int = if (minLines > 1) Int.MAX_VALUE else 1,
    enabled: Boolean = true,
    readOnly: Boolean = false,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    interactionSource: MutableInteractionSource? = null,
) {
    val source = interactionSource ?: remember { MutableInteractionSource() }
    val colors = pemaFieldColors()
    val style = PemaType.input
    BasicTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier.fillMaxWidth().defaultMinSize(minHeight = 56.dp),
        enabled = enabled,
        readOnly = readOnly,
        textStyle = style,
        cursorBrush = SolidColor(PemaColors.Blue),
        keyboardOptions = keyboardOptions,
        visualTransformation = visualTransformation,
        interactionSource = source,
        singleLine = maxLines == 1,
        minLines = minLines,
        maxLines = maxLines,
    ) { inner ->
        OutlinedTextFieldDefaults.DecorationBox(
            value = value,
            innerTextField = inner,
            enabled = enabled,
            singleLine = maxLines == 1,
            visualTransformation = visualTransformation,
            interactionSource = source,
            label = label?.let { { Text(it) } },
            placeholder = hint?.let { { Text(it, style = style.copy(color = PemaColors.OnSurfaceVariant)) } },
            leadingIcon = prefixIcon?.let { { PemaIcon(it, size = 24.dp, color = PemaColors.OnSurfaceVariant) } },
            trailingIcon = suffix,
            colors = colors,
            container = {
                OutlinedTextFieldDefaults.Container(
                    enabled = enabled,
                    isError = false,
                    interactionSource = source,
                    colors = colors,
                    shape = Radius14,
                    focusedBorderThickness = 1.5.dp,
                    unfocusedBorderThickness = 1.dp,
                )
            },
        )
    }
}

@Composable
internal fun pemaFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedContainerColor = Color.White,
    unfocusedContainerColor = Color.White,
    disabledContainerColor = Color.White,
    focusedBorderColor = PemaColors.Blue,
    unfocusedBorderColor = PemaColors.FieldBorder,
    disabledBorderColor = PemaColors.FieldBorderDefault,
    focusedLabelColor = PemaColors.Blue,
    unfocusedLabelColor = PemaColors.OnSurfaceVariant,
    focusedTextColor = PemaColors.OnSurface,
    unfocusedTextColor = PemaColors.OnSurface,
    focusedPlaceholderColor = PemaColors.OnSurfaceVariant,
    unfocusedPlaceholderColor = PemaColors.OnSurfaceVariant,
    focusedLeadingIconColor = PemaColors.OnSurfaceVariant,
    unfocusedLeadingIconColor = PemaColors.OnSurfaceVariant,
    cursorColor = PemaColors.Blue,
)

/** Search box used by PatientSearch: prefix `search`, hint "Tìm tên hoặc mã hồ sơ". */
@Composable
fun PemaSearchField(value: String, onValueChange: (String) -> Unit, modifier: Modifier = Modifier, hint: String = "Tìm tên hoặc mã hồ sơ") {
    PemaTextField(value, onValueChange, modifier, hint = hint, prefixIcon = "search")
}

/**
 * Flutter `DropdownButtonFormField` under AppTheme · canvas `dd`: 56 high,
 * white, #CADBE8 border, filled `arrow_drop_down`, floating [label].
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun <T> PemaDropdownField(
    value: T,
    options: List<T>,
    onSelected: (T) -> Unit,
    modifier: Modifier = Modifier,
    label: String? = null,
    display: (T) -> String = { it.toString() },
    enabled: Boolean = true,
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { if (enabled) expanded = it }, modifier = modifier) {
        PemaTextField(
            value = display(value),
            onValueChange = {},
            readOnly = true,
            enabled = enabled,
            label = label,
            suffix = { PemaIcon("arrow_drop_down", size = 24.dp, color = PemaColors.OnSurfaceVariant, filled = true) },
            modifier = Modifier.menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable, enabled),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }, containerColor = PemaColors.SurfaceContainer) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(display(option), style = PemaType.input, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    onClick = { expanded = false; onSelected(option) },
                )
            }
        }
    }
}

/** Canvas `chips` item · M3 `FilterChip` / `ChoiceChip`: 32 high, radius 8, check when selected. */
@Composable
fun PemaFilterChip(label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    FilterChip(
        selected = selected,
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        label = { Text(label, style = PemaType.label) },
        leadingIcon = if (selected) ({ PemaIcon("check", size = 18.dp) }) else null,
        shape = RoundedCornerShape(8.dp),
        colors = FilterChipDefaults.filterChipColors(
            labelColor = PemaColors.OnSurfaceVariant,
            selectedContainerColor = PemaColors.SecondaryContainer,
            selectedLabelColor = PemaColors.OnSecondaryContainer,
            selectedLeadingIconColor = PemaColors.OnSecondaryContainer,
            disabledLabelColor = PemaColors.DisabledContent,
        ),
        border = FilterChipDefaults.filterChipBorder(
            enabled = enabled,
            selected = selected,
            borderColor = PemaColors.OutlineVariant,
            disabledBorderColor = PemaColors.Disabled,
        ),
    )
}

/** Canvas `chips`: wrap of chips, 8dp column gap, each in a 48dp touch row. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PemaChipWrap(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    FlowRow(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.Center) { content() }
}

/** Canvas `inputChip` · M3 `InputChip` with a delete icon. */
@Composable
fun PemaInputChip(label: String, onDelete: () -> Unit, modifier: Modifier = Modifier) {
    InputChip(
        selected = false,
        onClick = onDelete,
        modifier = modifier,
        label = { Text(label, style = PemaType.of(12f, androidx.compose.ui.text.font.FontWeight.W500, PemaColors.OnSurfaceVariant)) },
        trailingIcon = { PemaIcon("close", size = 18.dp, color = PemaColors.OnSurfaceVariant) },
        shape = RoundedCornerShape(8.dp),
        colors = InputChipDefaults.inputChipColors(labelColor = PemaColors.OnSurfaceVariant),
        border = InputChipDefaults.inputChipBorder(enabled = true, selected = false, borderColor = PemaColors.OutlineVariant),
    )
}

/** Canvas `check` · Flutter `CheckboxListTile`: 56 min height, label 16/24, checkbox trailing. */
@Composable
fun PemaCheckRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Row(
        modifier
            .fillMaxWidth()
            .heightIn(min = 56.dp)
            .toggleable(value = checked, enabled = enabled, role = Role.Checkbox, onValueChange = onCheckedChange)
            .padding(start = 16.dp, end = 24.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(label, style = PemaType.input, modifier = Modifier.weight(1f))
        CompositionLocalProvider(LocalMinimumInteractiveComponentSize provides 0.dp) {
            Checkbox(
                checked = checked,
                onCheckedChange = null,
                enabled = enabled,
                colors = CheckboxDefaults.colors(
                    checkedColor = PemaColors.Blue,
                    uncheckedColor = PemaColors.OnSurfaceVariant,
                    checkmarkColor = Color.White,
                ),
            )
        }
    }
}

/** A white, 18-radius card with #E3ECF3 border – the base of tile-like custom rows. */
@Composable
fun PemaCard(
    modifier: Modifier = Modifier,
    borderColor: Color = PemaColors.TileBorder,
    radius: Int = 18,
    padding: PaddingValues = PaddingValues(16.dp),
    content: @Composable () -> Unit,
) {
    val shape = RoundedCornerShape(radius.dp)
    Box(modifier.fillMaxWidth().background(Color.White, shape).border(1.dp, borderColor, shape).padding(padding)) { content() }
}
