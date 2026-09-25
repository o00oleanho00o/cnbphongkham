package com.pema.clinic.feature.orders

import com.pema.clinic.core.common.AppNavigator
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.hardware.FakePlatformServices
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.billing.ReceiptsStore
import com.pema.clinic.shared.care.CareQueue
import com.pema.clinic.shared.care.ReviewQueue
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import com.pema.clinic.shared.finance.FinanceActor
import com.pema.clinic.shared.finance.FinanceRepository
import com.pema.clinic.shared.finance.FinanceSnapshot
import com.pema.clinic.shared.finance.FinanceStore
import com.pema.clinic.shared.finance.ProcedureEntry
import com.pema.clinic.shared.orders.OrdersStore
import com.pema.clinic.shared.patients.PatientsStore
import com.pema.clinic.shared.session.SessionStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class OrdersLogicTest {
    @Test
    fun catalogDraftApprovalAndPatientIsolationMatchFlutter() {
        val fixture = ordersFixture()
        val catalog = fixture.catalog.catalog()
        val id = fixture.sessionStore.selectedPatientId()
        val product = catalog.products.first()

        fixture.patientsStore.addToCart(id, product)
        assertFalse(fixture.patientsStore.of(id).cartReady)
        assertFailsWith<IllegalStateException> {
            fixture.ordersStore.save(id, approve = true)
        }

        fixture.patientsStore.updateLine(id, 0) {
            it.copy(usage = "Hướng dẫn được bác sĩ kiểm tra")
        }
        assertTrue(fixture.patientsStore.of(id).cartReady)

        fixture.ordersStore.save(id, approve = false)
        assertFalse(fixture.ordersStore.patientOrders(id).single().approved)
        assertTrue(fixture.patientsStore.of(id).cart.isEmpty())

        fixture.ordersStore.edit(id, fixture.ordersStore.patientOrders(id).single())
        fixture.ordersStore.save(id, approve = true)

        assertEquals(1, fixture.ordersStore.patientOrders(id).size)
        assertTrue(fixture.ordersStore.patientOrders(id).single().approved)
        assertEquals(product.price, fixture.ordersStore.patientOrders(id).single().total)

        fixture.sessionStore.select(1)
        assertTrue(fixture.ordersStore.patientOrders(fixture.sessionStore.selectedPatientId()).isEmpty())
    }

    @Test
    fun savingAnotherPatientDoesNotChangeThisPatientOrderList() {
        val fixture = ordersFixture()
        val catalog = fixture.catalog.catalog()
        val a = catalog.patientIds[0]
        val b = catalog.patientIds[1]

        fixture.patientsStore.addToCart(b, catalog.products.first())
        fixture.ordersStore.save(b, approve = false)
        assertTrue(fixture.ordersStore.patientOrders(a).isEmpty())

        fixture.patientsStore.addToCart(a, catalog.products.first())
        fixture.ordersStore.save(a, approve = false)
        assertEquals(1, fixture.ordersStore.patientOrders(a).size)
        assertEquals("DN-2", fixture.ordersStore.patientOrders(a).single().id)
    }

    @Test
    fun quickOrderSearchTakesTwentyAndReviewButtonUsesCartTotals() {
        val fixture = ordersFixture()
        val catalog = fixture.catalog.catalog()
        val profile = catalog.profiles.first()
        val patient = fixture.patientsStore.of(profile.id)

        val empty = buildQuickOrderState(profile, patient, catalog.products, "")
        assertEquals(20, empty.products.size)
        assertEquals(115, empty.catalogCount)
        assertEquals(0, empty.cartCount)
        assertEquals(0, empty.cartTotal)

        val query = catalog.products.first().code.lowercase()
        val filtered = buildQuickOrderState(profile, patient, catalog.products, query)
        assertTrue(filtered.products.isNotEmpty())
        assertTrue(filtered.products.all { it.matches(query) })
    }

    @Test
    fun orderReviewReadyRequiresRouteAndUsageForEveryLine() {
        val fixture = ordersFixture()
        val catalog = fixture.catalog.catalog()
        val profile = catalog.profiles.first()
        val id = profile.id
        val product = catalog.products.first()

        fixture.patientsStore.addToCart(id, product)
        val notReady = buildOrderReviewState(profile, fixture.patientsStore.of(id))
        assertEquals(1, notReady.cartCount)
        assertFalse(notReady.cartReady)

        fixture.patientsStore.updateLine(id, 0) { it.copy(usage = "Hướng dẫn mẫu bác sĩ đã xem") }
        val ready = buildOrderReviewState(profile, fixture.patientsStore.of(id))
        assertTrue(ready.cartReady)
        assertEquals(product.price, ready.cartTotal)
    }

    @Test
    fun prescriptionsFilterDraftsOnlyForCareModeAndEditDraftNavigatesToReview() {
        val fixture = ordersFixture()
        val catalog = fixture.catalog.catalog()
        val id = fixture.sessionStore.selectedPatientId()
        val product = catalog.products.first()

        fixture.patientsStore.addToCart(id, product)
        fixture.ordersStore.save(id, approve = false)
        val draft = fixture.ordersStore.patientOrders(id).single()

        val clinic = buildPrescriptionsState(
            careMode = false,
            profile = catalog.profile(id),
            orders = fixture.ordersStore.state.value,
        )
        assertEquals(1, clinic.visibleOrders.size)
        assertFalse(clinic.visibleOrders.single().approved)

        val care = buildPrescriptionsState(
            careMode = true,
            profile = catalog.profile(id),
            orders = fixture.ordersStore.state.value,
        )
        assertTrue(care.visibleOrders.isEmpty())

        val vm = OrdersViewModel(fixture.deps)
        vm.edit(draft)
        assertEquals(Routes.OrderReview, fixture.navigator.opened.single())
        assertEquals(draft.id, fixture.patientsStore.of(id).editingOrder)
        assertEquals(1, fixture.patientsStore.of(id).cart.size)
    }

    @Test
    fun approveSavesOneOrderAndNavigatesToPrescriptions() {
        val fixture = ordersFixture()
        val id = fixture.sessionStore.selectedPatientId()
        val product = fixture.catalog.catalog().products.first()
        fixture.patientsStore.addToCart(id, product)
        fixture.patientsStore.updateLine(id, 0) { it.copy(usage = "Hướng dẫn được bác sĩ kiểm tra") }

        val vm = OrdersViewModel(fixture.deps)
        vm.approve()

        assertEquals(listOf(Routes.Prescriptions), fixture.navigator.opened)
        assertTrue(fixture.ordersStore.patientOrders(id).single().approved)
        assertTrue(fixture.patientsStore.of(id).cart.isEmpty())
    }
}

private data class OrdersFixture(
    val deps: FeatureDeps,
    val navigator: RecordingNavigator,
    val catalog: MutableCatalogRepository,
    val sessionStore: SessionStore,
    val patientsStore: PatientsStore,
    val ordersStore: OrdersStore,
)

private fun ordersFixture(): OrdersFixture {
    val navigator = RecordingNavigator()
    val catalog = MutableCatalogRepository()
    val sessionStore = SessionStore(catalog)
    val patientsStore = PatientsStore(catalog)
    val ordersStore = OrdersStore(patientsStore, catalog)
    val scope = CoroutineScope(StandardTestDispatcher())
    val deps = FeatureDeps(
        navigator = navigator,
        platform = FakePlatformServices(),
        catalogRepository = catalog,
        sessionStore = sessionStore,
        patientsStore = patientsStore,
        ordersStore = ordersStore,
        receiptsStore = ReceiptsStore(sessionStore, ordersStore),
        careQueue = CareQueue(catalog, patientsStore, scope),
        reviewQueue = ReviewQueue(catalog, patientsStore, sessionStore, scope),
        financeStore = FinanceStore(NoopFinanceRepository, scope),
    )
    return OrdersFixture(deps, navigator, catalog, sessionStore, patientsStore, ordersStore)
}

private class RecordingNavigator : AppNavigator {
    val opened = mutableListOf<String>()
    var backCount = 0

    override fun go(route: String) {
        opened += route
    }

    override fun back() {
        backCount++
    }
}

private object NoopFinanceRepository : FinanceRepository {
    override suspend fun getState(month: String, actor: FinanceActor): FinanceSnapshot = error("Not used")
    override suspend fun approveEntry(id: String, actor: FinanceActor) = Unit
    override suspend fun voidEntry(id: String, reason: String, actor: FinanceActor) = Unit
    override suspend fun recordEntry(entry: ProcedureEntry, actor: FinanceActor) = Unit
    override suspend fun recordPayment(key: String, invoice: String, amount: Int, method: String, actor: FinanceActor) = Unit
    override suspend fun closePeriod(month: String, actor: FinanceActor) = Unit
    override suspend fun markPeriodPaid(month: String, reference: String, actor: FinanceActor) = Unit
    override suspend fun updateRate(service: String, rate: Int, basis: String, actor: FinanceActor) = Unit
    override suspend fun markNotificationRead(id: String, actor: FinanceActor) = Unit
}
