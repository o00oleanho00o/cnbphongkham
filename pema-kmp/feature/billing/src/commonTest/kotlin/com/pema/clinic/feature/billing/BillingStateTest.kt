package com.pema.clinic.feature.billing

import com.pema.clinic.shared.billing.ReceiptsStore
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import com.pema.clinic.shared.catalog.sampleCatalog
import com.pema.clinic.shared.orders.OrdersStore
import com.pema.clinic.shared.patients.PatientsStore
import com.pema.clinic.shared.session.Session
import com.pema.clinic.shared.session.SessionStore
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class BillingStateTest {
    @Test
    fun currentBillSumsTheSelectedPatientOrders() {
        val stores = billingStores()
        val id = stores.session.selectedPatientId()
        val product = stores.catalog.catalog().products[1]

        stores.patients.addToCart(id, product)
        stores.patients.addToCart(id, product)
        stores.orders.save(id, approve = false)

        val bill = stores.receipts.currentBill()
        assertEquals(product.price * 2, bill.total)
        assertEquals(product.price * 2, bill.due)
        assertFalse(bill.settled)
    }

    @Test
    fun receiptsAndOrdersAreScopedPerPatient() {
        val stores = billingStores()
        val firstId = stores.session.selectedPatientId()
        val product = stores.catalog.catalog().products.first()
        stores.patients.addToCart(firstId, product)
        stores.orders.save(firstId, approve = false)

        stores.receipts.settle(firstId, 100)
        assertEquals(100, stores.receipts.currentPaid())
        assertEquals(stores.orders.patientOrders(firstId).single().total - 100, stores.receipts.currentBill().due)

        stores.session.select(1)
        assertEquals(0, stores.receipts.currentPaid())
        assertEquals(0, stores.receipts.currentBill().total)
        assertTrue(stores.receipts.currentBill().settled)
        assertEquals(100, stores.receipts.paidFor(firstId))
    }

    @Test
    fun selectedPatientControlsWhichOrderLinesAppear() {
        val stores = billingStores()
        val firstId = stores.catalog.catalog().patientIds[0]
        val secondId = stores.catalog.catalog().patientIds[1]
        val product = stores.catalog.catalog().products[2]

        stores.patients.addToCart(secondId, product)
        stores.orders.save(secondId, approve = false)

        val firstState = buildCashierState(
            session = stores.session.state.value,
            profile = stores.catalog.profile(firstId),
            orders = stores.orders.patientOrders(firstId),
            paid = stores.receipts.paidFor(firstId),
        )
        assertEquals(0, firstState.bill.total)
        assertTrue(firstState.invoiceLines.isEmpty())

        stores.session.select(1)
        val secondState = buildCashierState(
            session = stores.session.state.value,
            profile = stores.catalog.profile(secondId),
            orders = stores.orders.patientOrders(secondId),
            paid = stores.receipts.paidFor(secondId),
        )
        assertEquals(product.price, secondState.bill.total)
        assertEquals(listOf("DN-1"), secondState.invoiceLines.map { it.id })
    }

    @Test
    fun actionVisibilityFollowsFlutterSessionRoles() {
        val stores = billingStores()
        val profile = stores.catalog.catalog().profiles.first()
        val id = profile.id
        val product = stores.catalog.catalog().products[3]
        stores.patients.addToCart(id, product)
        stores.orders.save(id, approve = false)
        val orders = stores.orders.patientOrders(id)

        val owner = buildCashierState(Session(), profile, orders, paid = 0)
        assertTrue(owner.showCollectAction)
        assertTrue(owner.collectEnabled)
        assertTrue(owner.showNewOrderAction)

        val accountant = buildCashierState(Session(staffRole = "accountant"), profile, orders, paid = 0)
        assertTrue(accountant.showCollectAction)
        assertTrue(accountant.collectEnabled)
        assertFalse(accountant.showNewOrderAction)

        val doctor = buildCashierState(Session(staffRole = "doctor"), profile, orders, paid = 0)
        assertFalse(doctor.showCollectAction)
        assertFalse(doctor.collectEnabled)
        assertTrue(doctor.showNewOrderAction)

        val care = buildCashierState(Session(careMode = true), profile, orders, paid = 0)
        assertFalse(care.showCollectAction)
        assertFalse(care.collectEnabled)
        assertFalse(care.showNewOrderAction)
        assertEquals(product.price, care.bill.due)
        assertEquals("DN-1", care.invoiceLines.single().id)
    }

    @Test
    fun collectingTheFullTotalSettlesTheBillAndDisablesCollection() {
        val stores = billingStores()
        val profile = stores.catalog.catalog().profiles.first()
        val product = stores.catalog.catalog().products[4]
        stores.patients.addToCart(profile.id, product)
        stores.orders.save(profile.id, approve = false)

        val total = stores.receipts.billFor(profile.id).total
        stores.receipts.settle(profile.id, total)

        val state = buildCashierState(
            session = Session(),
            profile = profile,
            orders = stores.orders.patientOrders(profile.id),
            paid = stores.receipts.paidFor(profile.id),
        )
        assertEquals(0, state.bill.due)
        assertTrue(state.bill.settled)
        assertTrue(state.showCollectAction)
        assertFalse(state.collectEnabled)
    }

    private data class Stores(
        val catalog: MutableCatalogRepository,
        val patients: PatientsStore,
        val orders: OrdersStore,
        val session: SessionStore,
        val receipts: ReceiptsStore,
    )

    private fun billingStores(): Stores {
        val catalog = MutableCatalogRepository(sampleCatalog())
        val patients = PatientsStore(catalog)
        val orders = OrdersStore(patients, catalog)
        val session = SessionStore(catalog)
        val receipts = ReceiptsStore(session, orders)
        return Stores(catalog, patients, orders, session, receipts)
    }
}
