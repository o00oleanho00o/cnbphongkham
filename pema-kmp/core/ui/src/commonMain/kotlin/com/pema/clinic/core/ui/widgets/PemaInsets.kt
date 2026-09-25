package com.pema.clinic.core.ui.widgets

import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.statusBars
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf

/**
 * Overrides the system bar insets (status bar on top, home indicator /
 * navigation bar at the bottom). Only the screenshot harness sets it so a
 * render matches the canvas phone frame (bottom 34dp); on devices it stays
 * null and the real window insets are used.
 */
val LocalSystemInsetsOverride = staticCompositionLocalOf<WindowInsets?> { null }

/** Status bar inset – use instead of `WindowInsets.statusBars`. */
val pemaStatusBars: WindowInsets
    @Composable
    get() = LocalSystemInsetsOverride.current?.only(WindowInsetsSides.Top) ?: WindowInsets.statusBars

/** Navigation bar / home indicator inset – use instead of `WindowInsets.navigationBars`. */
val pemaNavigationBars: WindowInsets
    @Composable
    get() = LocalSystemInsetsOverride.current?.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal)
        ?: WindowInsets.navigationBars
