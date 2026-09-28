package com.pema.clinic

import com.pema.clinic.core.common.Routes
import com.pema.clinic.shared.session.Session
import kotlin.test.Test
import kotlin.test.assertEquals

/** Flutter `AppRouter.onGenerateRoute` + `_RouteGuard` rules, applied by the shell navigator. */
class ShellRoutesTest {
    private val owner = Session()
    private val doctor = Session(staffRole = "doctor")
    private val cskh = Session(staffRole = "care", staffName = "CSKH")
    private val care = Session(careMode = true)

    @Test
    fun ownerOpensEveryKnownRoute() {
        for (id in Routes.flutterRoutes - Routes.Finance - Routes.Guide) assertEquals(id, resolveRoute(id, owner))
    }

    @Test
    fun flutterRouteNamesResolveToIds() {
        assertEquals(Routes.Patient360, resolveRoute("Patient 360", owner))
        assertEquals(Routes.Prescriptions, resolveRoute("Đơn thuốc & tư vấn", owner))
    }

    @Test
    fun blockedRoutesOpenTheGuardScreen() {
        assertEquals(Routes.denied("Thu ngân"), resolveRoute(Routes.Cashier, doctor))
        assertEquals(Routes.denied("Patient 360"), resolveRoute(Routes.Patient360, care))
        assertEquals(Routes.CustomerCare, resolveRoute(Routes.CustomerCare, cskh))
    }

    @Test
    fun unknownRoutesOpenTheGuideUnlessBlocked() {
        assertEquals(Routes.guide("Việc lạ"), resolveRoute("Việc lạ", owner))
        assertEquals(Routes.denied("Việc lạ"), resolveRoute("Việc lạ", cskh))
        assertEquals(Routes.guide("Hướng dẫn"), resolveRoute(Routes.Guide, care))
    }

    @Test
    fun financeIsNotGuarded() {
        assertEquals(Routes.finance(0), resolveRoute(Routes.Finance, care))
        assertEquals(Routes.finance(3), resolveRoute(Routes.finance(3), doctor))
        assertEquals(Routes.FinanceRates, resolveRoute(Routes.FinanceRates, doctor))
    }

    @Test
    fun argsArePercentEncoded() {
        assertEquals("guide?route=%C4%90%C6%A1n%20thu%E1%BB%91c%20%26%20t%C6%B0%20v%E1%BA%A5n", Routes.guide("Đơn thuốc & tư vấn"))
    }
}
