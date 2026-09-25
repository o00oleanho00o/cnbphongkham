package com.pema.clinic.feature.finance

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.getValue
import androidx.compose.material3.SnackbarResult
import androidx.lifecycle.compose.LifecycleResumeEffect
import com.pema.clinic.core.ui.widgets.LocalPemaSnackbar
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.PaymentAlertLogic
import kotlinx.coroutines.flow.collect

@Composable
fun PaymentAlerts(deps: FeatureDeps, content: @Composable () -> Unit) {
    val snackbar = LocalPemaSnackbar.current
    val currentDeps by rememberUpdatedState(deps)

    DisposableEffect(deps.financeStore) {
        deps.financeStore.start()
        onDispose { deps.financeStore.stop() }
    }
    LifecycleResumeEffect(deps.financeStore) {
        deps.financeStore.setForeground(true)
        onPauseOrDispose { deps.financeStore.setForeground(false) }
    }
    LaunchedEffect(deps.financeStore, deps.sessionStore, snackbar) {
        var previous: FinanceState? = null
        deps.financeStore.state.collect { next ->
            if (PaymentAlertLogic.shouldNotify(
                    enabled = true,
                    session = currentDeps.sessionStore.state.value,
                    previous = previous,
                    next = next,
                )
            ) {
                val result = snackbar.showSnackbar(
                    message = PaymentAlertLogic.message,
                    actionLabel = PaymentAlertLogic.actionLabel,
                )
                if (result == SnackbarResult.ActionPerformed) {
                    currentDeps.navigator.openFinance(PaymentAlertLogic.financeTab)
                }
            }
            previous = next
        }
    }

    content()
}
