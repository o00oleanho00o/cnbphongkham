package com.pema.clinic.core.ui.theme

import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.pema.clinic.core.ui.widgets.LocalPemaIconMeasurer
import com.pema.clinic.core.ui.generated.resources.Res
import com.pema.clinic.core.ui.generated.resources.be_vietnam_pro_bold
import com.pema.clinic.core.ui.generated.resources.be_vietnam_pro_medium
import com.pema.clinic.core.ui.generated.resources.be_vietnam_pro_regular
import com.pema.clinic.core.ui.generated.resources.be_vietnam_pro_semibold
import com.pema.clinic.core.ui.generated.resources.material_icons_filled
import com.pema.clinic.core.ui.generated.resources.material_icons_outlined
import org.jetbrains.compose.resources.Font

/**
 * Flutter `AppTheme.light`: M3, `ColorScheme.fromSeed(#0B4F94, primary: blue,
 * surface: white)`, Be Vietnam Pro, paper scaffold, bodyMedium 14/1.5 ink.
 */
val PemaColorScheme = lightColorScheme(
    primary = PemaColors.Blue,
    onPrimary = Color.White,
    primaryContainer = PemaColors.PrimaryContainer,
    onPrimaryContainer = PemaColors.OnPrimaryContainer,
    inversePrimary = PemaColors.InversePrimary,
    secondary = PemaColors.Secondary,
    onSecondary = Color.White,
    secondaryContainer = PemaColors.SecondaryContainer,
    onSecondaryContainer = PemaColors.OnSecondaryContainer,
    tertiary = PemaColors.Tertiary,
    onTertiary = Color.White,
    tertiaryContainer = PemaColors.TertiaryContainer,
    onTertiaryContainer = PemaColors.OnTertiaryContainer,
    background = PemaColors.Paper,
    onBackground = PemaColors.OnSurface,
    surface = Color.White,
    onSurface = PemaColors.OnSurface,
    surfaceVariant = PemaColors.SurfaceVariant,
    onSurfaceVariant = PemaColors.OnSurfaceVariant,
    surfaceTint = PemaColors.Blue,
    inverseSurface = PemaColors.InverseSurface,
    inverseOnSurface = PemaColors.InverseOnSurface,
    error = PemaColors.Error,
    onError = Color.White,
    errorContainer = PemaColors.ErrorContainer,
    onErrorContainer = PemaColors.OnErrorContainer,
    outline = PemaColors.Outline,
    outlineVariant = PemaColors.OutlineVariant,
    scrim = Color.Black,
    surfaceBright = Color.White,
    surfaceDim = PemaColors.SurfaceDim,
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = PemaColors.SurfaceContainerLow,
    surfaceContainer = PemaColors.SurfaceContainer,
    surfaceContainerHigh = PemaColors.SurfaceContainerHigh,
    surfaceContainerHighest = PemaColors.SurfaceContainerHighest,
)

/** Fonts bundled from `flutter-template/assets` + Material Icons (outlined / filled). */
@Immutable
data class PemaFonts(val text: FontFamily, val iconsOutlined: FontFamily, val iconsFilled: FontFamily)

val LocalPemaFonts = staticCompositionLocalOf<PemaFonts> { error("Wrap content in PemaTheme") }

/** Flutter's line boxes distribute leading proportionally and never trim. */
internal val FlutterLineHeight = LineHeightStyle(LineHeightStyle.Alignment.Proportional, LineHeightStyle.Trim.None)

/** `TextStyle(fontSize, height)` like Flutter: [height] is a multiplier of [size]. */
fun pemaStyle(
    size: Float,
    weight: FontWeight = FontWeight.W400,
    color: Color = Color.Unspecified,
    height: Float = 1.5f,
    letterSpacing: TextUnit = 0.sp,
): TextStyle = TextStyle(
    fontSize = size.sp,
    fontWeight = weight,
    color = color,
    lineHeight = (size * height).sp,
    letterSpacing = letterSpacing,
    lineHeightStyle = FlutterLineHeight,
)

/**
 * Text styles of the Pema blocks, values from the canvas "KIỂU CHỮ" card and
 * `pema_blocks.dart`. Font family comes from [PemaTheme] (LocalTextStyle), so
 * use them as `style = PemaType.heading`.
 */
object PemaType {
    @Composable @ReadOnlyComposable
    private fun withFont(style: TextStyle) = style.copy(fontFamily = LocalPemaFonts.current.text)

    /** Any other Flutter `TextStyle(fontSize, fontWeight, color, height)` in Be Vietnam Pro. */
    @Composable @ReadOnlyComposable
    fun of(
        size: Float,
        weight: FontWeight = FontWeight.W400,
        color: Color = Color.Unspecified,
        height: Float = 1.5f,
        letterSpacing: TextUnit = 0.sp,
    ): TextStyle = withFont(pemaStyle(size, weight, color, height, letterSpacing))

    val heading: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(25f, FontWeight.W700, PemaColors.Navy, height = 1.3f))
    val h2: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(26f, FontWeight.W700, PemaColors.Ink, height = 1.25f))
    val section: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(17f, FontWeight.W700, PemaColors.Ink, height = 1.3f))
    val heroTitle: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(24f, FontWeight.W600, Color.White, height = 1.3f))
    val heroKicker: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(10f, color = PemaColors.HeroKicker, letterSpacing = 1.4.sp))
    val heroSub: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(12f, color = PemaColors.HeroSub))
    val metricValue: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(28f, FontWeight.W700, PemaColors.Blue, height = 1.3f))
    val tileTitle: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(14f, FontWeight.W600, PemaColors.OnSurface))
    val tileSub: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(12f, color = PemaColors.Muted, height = 1.43f))
    val body: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(14f, color = PemaColors.Ink))
    val bodyStrong: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(14f, FontWeight.W600, PemaColors.Ink))
    val sub13: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(13f, color = PemaColors.Muted))
    val caption: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(12f, color = PemaColors.Muted))
    val captionInk: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(12f, color = PemaColors.Ink))
    val small: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(11f, color = PemaColors.Muted))
    val notice: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(12f, color = PemaColors.Navy))
    val label: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(14f, FontWeight.W500, letterSpacing = 0.1.sp, height = 20f / 14f))
    val input: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(16f, color = PemaColors.OnSurface, height = 1.5f))
    val appBarTitle: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(18f, FontWeight.W600, PemaColors.Ink, height = 1.3f))
    val financeTitle: TextStyle @Composable @ReadOnlyComposable get() = withFont(pemaStyle(18f, FontWeight.W700, PemaColors.Ink))
}

/** Material 3 (2021) type scale – identical in Flutter and Compose – in Be Vietnam Pro. */
private fun pemaTypography(family: FontFamily): Typography {
    val base = Typography()
    fun TextStyle.f() = copy(fontFamily = family, lineHeightStyle = FlutterLineHeight)
    return Typography(
        displayLarge = base.displayLarge.f(),
        displayMedium = base.displayMedium.f(),
        displaySmall = base.displaySmall.f(),
        headlineLarge = base.headlineLarge.f(),
        headlineMedium = base.headlineMedium.f(),
        headlineSmall = base.headlineSmall.f(),
        titleLarge = base.titleLarge.f(),
        titleMedium = base.titleMedium.f(),
        titleSmall = base.titleSmall.f(),
        bodyLarge = base.bodyLarge.f(),
        // Flutter override: TextStyle(color: ink, fontSize: 14, height: 1.5)
        bodyMedium = base.bodyMedium.f().copy(color = PemaColors.Ink, fontSize = 14.sp, lineHeight = 21.sp, letterSpacing = 0.em),
        bodySmall = base.bodySmall.f(),
        labelLarge = base.labelLarge.f(),
        labelMedium = base.labelMedium.f(),
        labelSmall = base.labelSmall.f(),
    )
}

@Composable
fun rememberPemaFonts(): PemaFonts = PemaFonts(
    text = FontFamily(
        Font(Res.font.be_vietnam_pro_regular, FontWeight.W400),
        Font(Res.font.be_vietnam_pro_medium, FontWeight.W500),
        Font(Res.font.be_vietnam_pro_semibold, FontWeight.W600),
        Font(Res.font.be_vietnam_pro_bold, FontWeight.W700),
    ),
    iconsOutlined = FontFamily(Font(Res.font.material_icons_outlined)),
    iconsFilled = FontFamily(Font(Res.font.material_icons_filled)),
)

/**
 * App theme. Like Flutter, plain `Text()` renders bodyMedium (14/21, ink,
 * Be Vietnam Pro), and icons default to ink.
 */
@Composable
fun PemaTheme(content: @Composable () -> Unit) {
    val fonts = rememberPemaFonts()
    val typography = pemaTypography(fonts.text)
    val iconMeasurer = rememberTextMeasurer(cacheSize = 128)
    MaterialTheme(colorScheme = PemaColorScheme, typography = typography) {
        CompositionLocalProvider(
            LocalPemaFonts provides fonts,
            LocalPemaIconMeasurer provides iconMeasurer,
            LocalTextStyle provides typography.bodyMedium,
            LocalContentColor provides PemaColors.Ink,
            content = content,
        )
    }
}
