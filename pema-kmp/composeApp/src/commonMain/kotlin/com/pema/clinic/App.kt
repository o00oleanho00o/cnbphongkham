package com.pema.clinic

import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.material3.SnackbarHostState
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import androidx.savedstate.read
import com.pema.clinic.core.common.ApiConfig
import com.pema.clinic.core.common.AppNavigator
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.hardware.LocalPlatformServices
import com.pema.clinic.core.hardware.rememberPlatformServices
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaTheme
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.core.ui.widgets.LocalPemaMessenger
import com.pema.clinic.core.ui.widgets.LocalPemaSnackbar
import com.pema.clinic.core.ui.widgets.PemaMessenger
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.feature.aftercare.aftercareGraph
import com.pema.clinic.feature.billing.billingGraph
import com.pema.clinic.feature.care.careGraph
import com.pema.clinic.feature.finance.PaymentAlerts
import com.pema.clinic.feature.finance.financeGraph
import com.pema.clinic.feature.orders.ordersGraph
import com.pema.clinic.feature.patients.patientsGraph
import com.pema.clinic.feature.schedule.scheduleGraph
import com.pema.clinic.feature.workspace.workspaceGraph
import com.pema.clinic.shared.session.Session

/**
 * Flutter `PemaApp` + `AppRouter`: always starts at Workspace, pushes task
 * screens by route, applies `_RouteGuard`, falls back to the Guide for unknown
 * routes and hosts `PaymentAlerts` above the navigator.
 */
@Composable
fun App(financeApi: String = ApiConfig.DEFAULT_FINANCE_API) {
    val platform = rememberPlatformServices()
    val navController = rememberNavController()
    val navigator = remember(navController) { ShellNavigator(navController) }
    val container = remember(platform, navigator, financeApi) { AppContainer(navigator, platform, financeApi) }
    navigator.session = { container.deps.sessionStore.state.value }
    val snackbar = remember { SnackbarHostState() }
    val rootScope = rememberCoroutineScope()
    val messenger = remember(snackbar, rootScope) { PemaMessenger(snackbar, rootScope) }

    CompositionLocalProvider(
        LocalPlatformServices provides platform,
        LocalPemaSnackbar provides snackbar,
        LocalPemaMessenger provides messenger,
        LocalOnBack provides navigator::back,
    ) {
        PemaTheme {
            PaymentAlerts(container.deps) {
                Box(Modifier.fillMaxSize().background(PemaColors.Paper)) {
                    NavHost(
                        navController = navController,
                        startDestination = Routes.Workspace,
                        enterTransition = { fadeIn(tween(220)) + scaleIn(tween(300), initialScale = 0.94f) },
                        exitTransition = { fadeOut(tween(160)) + scaleOut(tween(300), targetScale = 1.04f) },
                        popEnterTransition = { fadeIn(tween(220)) + scaleIn(tween(300), initialScale = 1.04f) },
                        popExitTransition = { fadeOut(tween(160)) + scaleOut(tween(300), targetScale = 0.94f) },
                    ) {
                        workspaceGraph(container.deps)
                        scheduleGraph(container.deps)
                        patientsGraph(container.deps)
                        aftercareGraph(container.deps)
                        ordersGraph(container.deps)
                        billingGraph(container.deps)
                        careGraph(container.deps)
                        financeGraph(container.deps)
                        composable(
                            Routes.DeniedPattern,
                            arguments = listOf(navArgument("route") { type = NavType.StringType; defaultValue = "" }),
                        ) { entry ->
                            DeniedScreen(entry.arguments?.read { getStringOrNull("route") }.orEmpty())
                        }
                    }
                }
            }
        }
    }
}

/** Flutter `_RouteGuard` body when `session.allows(route)` is false. */
@Composable
internal fun DeniedScreen(title: String) {
    DetailScaffold(title = title) {
        PemaNotice("Tác vụ không thuộc không gian hiện tại. Quay lại để chọn đúng công việc.")
    }
}

/**
 * Flutter `Navigator.pushNamed` + `AppRouter.onGenerateRoute`.
 * - `/finance` (with a tab) and the finance sub-pages are not guarded, as in Flutter.
 * - Known routes blocked by the current workspace open the guard screen.
 * - Unknown route names open `GuideScreen(route)`.
 */
internal class ShellNavigator(private val navController: NavHostController) : AppNavigator {
    var session: () -> Session? = { null }

    override fun go(route: String) {
        navController.navigate(resolveRoute(route, session())) { launchSingleTop = true }
    }

    override fun back() {
        if (navController.previousBackStackEntry != null) navController.popBackStack()
    }

    override fun openFinance(tab: Int) = go(Routes.finance(tab))
}

/** NavHost destination for [route] (id or Flutter route name) under [session]; see [ShellNavigator]. */
internal fun resolveRoute(route: String, session: Session?): String {
    fun guarded(title: String, target: String) =
        if (session?.allows(title) == false) Routes.denied(title) else target
    if (route.startsWith("finance?") || route.startsWith(Routes.FinanceProcedure) || route.startsWith(Routes.FinanceRates)) return route
    val id = if (route in Routes.all) route else Routes.idOf(route) ?: return guarded(route, Routes.guide(route))
    return when (id) {
        Routes.Finance -> Routes.finance(0)
        Routes.Workspace, Routes.SessionPicker -> id
        Routes.Guide -> guarded(Routes.titleOf(id), Routes.guide(Routes.titleOf(id)))
        else -> guarded(Routes.titleOf(id), id)
    }
}
