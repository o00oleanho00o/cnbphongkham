package com.pema.clinic.core.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Pema colour tokens, copied from Flutter `AppColors`, the literal colours in
 * `pema_blocks.dart` / `pema_bottom_nav.dart` / `app_theme.dart`, and the
 * Material 3 `ColorScheme.fromSeed(#0B4F94)` values that the design canvas
 * (`Pema App redesign canvas/Pema App.dc.html`) renders. Never invent colours:
 * if a screen needs one that is not here, take it from the canvas CSS.
 */
object PemaColors {
    // AppColors
    val Blue = Color(0xFF0B4F94)
    val Navy = Color(0xFF083A6E)
    val Sky = Color(0xFF3CAAE5)
    val Ink = Color(0xFF17324D)
    val Muted = Color(0xFF5D7184)
    val Paper = Color(0xFFF4F8FB)
    val Line = Color(0xFFE0EAF2)

    // Literal colours used by blocks
    val Tint = Color(0xFFE8F4FB) // avatar, notice, photo placeholder
    val TileBorder = Color(0xFFE3ECF3)
    val FieldBorder = Color(0xFFCADBE8) // enabled input / outlined button border
    val FieldBorderDefault = Color(0xFFD9E5EE) // InputDecoration.border, finance cards
    val HeroKicker = Color(0xFFB8DEF5)
    val HeroSub = Color(0xFFD7E9F5)
    val NavCapsule = Color(0xFFEAF4FC)
    val NavCapsuleBorder = Color(0xFFD0E6F9)
    val NavBorder = Color(0xFFE2E8F0)
    val NavIdle = Color(0xFF64748B)
    val PhotoIcon = Color(0xFF80B3D0)
    val CareAvatar = Color(0xFFEAF3FA)
    val FilterActive = Color(0xFFE2F1FB)
    val White = Color(0xFFFFFFFF)
    val Black54 = Color(0x8A000000)

    // Material 3 fromSeed(#0B4F94, primary = blue, surface = white) as rendered by Flutter
    val OnSurface = Color(0xFF1A1C20)
    val OnSurfaceVariant = Color(0xFF43474E)
    val Outline = Color(0xFF74777F)
    val OutlineVariant = Color(0xFFC3C6CF)
    val Error = Color(0xFFBA1A1A)
    val ErrorContainer = Color(0xFFFFDAD6)
    val OnErrorContainer = Color(0xFF410002)
    val PrimaryContainer = Color(0xFFD4E3FF)
    val OnPrimaryContainer = Color(0xFF001C3A)
    val Secondary = Color(0xFF535F70)
    val SecondaryContainer = Color(0xFFD5E3F8)
    val OnSecondaryContainer = Color(0xFF0E1D2F)
    val Tertiary = Color(0xFF6B5778)
    val TertiaryContainer = Color(0xFFF3DAFF)
    val OnTertiaryContainer = Color(0xFF251431)
    val SurfaceVariant = Color(0xFFDFE2EB)
    val SurfaceContainerLow = Color(0xFFF2F3FA)
    val SurfaceContainer = Color(0xFFECEEF4)
    val SurfaceContainerHigh = Color(0xFFE8EAF1)
    val SurfaceContainerHighest = Color(0xFFE2E2E9)
    val SurfaceDim = Color(0xFFD9D9E0)
    val InverseSurface = Color(0xFF2F3036)
    val InverseOnSurface = Color(0xFFF0F0F7)
    val InversePrimary = Color(0xFFA6C8FF)

    /** `rgba(26,28,32,.12)` – disabled container. */
    val Disabled = OnSurface.copy(alpha = 0.12f)

    /** `rgba(26,28,32,.38)` – disabled content. */
    val DisabledContent = OnSurface.copy(alpha = 0.38f)
}
