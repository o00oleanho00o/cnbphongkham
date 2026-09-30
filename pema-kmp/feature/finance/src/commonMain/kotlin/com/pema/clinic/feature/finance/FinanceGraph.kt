package com.pema.clinic.feature.finance

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import androidx.savedstate.read
import com.pema.clinic.core.common.Routes
import com.pema.clinic.shared.FeatureDeps
import kotlinx.coroutines.launch

fun NavGraphBuilder.financeGraph(deps: FeatureDeps) {
    composable(
        Routes.FinancePattern,
        arguments = listOf(navArgument("tab") { type = NavType.IntType; defaultValue = 0 }),
    ) { entry ->
        val tab = entry.arguments?.read { getIntOrNull("tab") } ?: 0
        FinanceRoute(
            deps = deps,
            initialTab = tab,
            lockRole = true,
            patientIds = deps.catalogRepository.catalog().patientIds,
        )
    }
    composable(Routes.FinanceProcedure) {
        ProcedureFormRoute(
            deps = deps,
            patientIds = deps.catalogRepository.catalog().patientIds,
        )
    }
    composable(Routes.FinanceRates) {
        RateRoute(deps)
    }
}

@Composable
private fun FinanceRoute(
    deps: FeatureDeps,
    initialTab: Int,
    lockRole: Boolean,
    patientIds: List<String>,
) {
    val state by deps.financeStore.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    LaunchedEffect(deps.financeStore) {
        deps.financeStore.refresh()
    }
    FinanceScreen(
        state = state,
        initialTab = initialTab,
        lockRole = lockRole,
        patientIds = patientIds,
        callbacks = FinanceCallbacks(
            refresh = { scope.launch { deps.financeStore.refresh() } },
            selectRole = deps.financeStore::select,
            setMonth = { month -> scope.launch { deps.financeStore.setMonth(month) } },
            approveEntry = deps.financeStore::approveEntry,
            voidEntry = deps.financeStore::voidEntry,
            recordPayment = { key, invoice, amount -> deps.financeStore.recordPayment(key = key, invoice = invoice, amount = amount) },
            closePeriod = deps.financeStore::closePeriod,
            markPeriodPaid = deps.financeStore::markPeriodPaid,
            markNotificationRead = deps.financeStore::markNotificationRead,
            openProcedureForm = { deps.navigator.go(Routes.FinanceProcedure) },
            openRateScreen = { deps.navigator.go(Routes.FinanceRates) },
        ),
    )
}

@Composable
private fun ProcedureFormRoute(
    deps: FeatureDeps,
    patientIds: List<String>,
) {
    val state by deps.financeStore.state.collectAsStateWithLifecycle()
    LaunchedEffect(deps.financeStore) {
        if (state.data == null) deps.financeStore.refresh()
    }
    ProcedureFormScreen(
        state = state,
        initialPatient = "P001",
        patientIds = patientIds,
        onSubmit = deps.financeStore::recordEntry,
        onDone = deps.navigator::back,
    )
}

@Composable
private fun RateRoute(deps: FeatureDeps) {
    val state by deps.financeStore.state.collectAsStateWithLifecycle()
    LaunchedEffect(deps.financeStore) {
        if (state.data == null) deps.financeStore.refresh()
    }
    RateScreen(
        state = state,
        onUpdateRate = deps.financeStore::updateRate,
    )
}
