package com.pema.clinic.core.ui.widgets

import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel

/** Holds a cleanup action until its ViewModelStore (the navigation back-stack entry) is cleared. */
class ScreenCleanup : ViewModel() {
    internal var action: (() -> Unit)? = null

    override fun onCleared() {
        action?.invoke()
        action = null
    }
}

/**
 * Runs [onCleared] when the current screen leaves the back stack – not on rotation or other
 * activity recreation (unlike `DisposableEffect`). Use it to delete temporary files such as an
 * unsent photo. [key] separates several cleanups on one screen.
 */
@Composable
fun OnScreenCleared(key: String, onCleared: () -> Unit) {
    val holder = viewModel(key = "screen-cleanup:$key") { ScreenCleanup() }
    SideEffect { holder.action = onCleared }
}
