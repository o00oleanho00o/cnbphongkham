package com.pema.clinic.shared

import com.pema.clinic.core.common.Routes
import com.pema.clinic.shared.billing.ReceiptsStore
import com.pema.clinic.shared.care.CareQueue
import com.pema.clinic.shared.care.CareQueueFilter
import com.pema.clinic.shared.care.ReviewQueue
import com.pema.clinic.shared.care.careGroups
import com.pema.clinic.shared.care.careNotContacted
import com.pema.clinic.shared.catalog.CatalogMapper
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import com.pema.clinic.shared.catalog.sampleCatalog
import com.pema.clinic.shared.finance.FinanceActor
import com.pema.clinic.shared.finance.FinanceInvoice
import com.pema.clinic.shared.finance.FinanceMapper
import com.pema.clinic.shared.finance.FinanceRepository
import com.pema.clinic.shared.finance.FinanceSnapshot
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.FinanceStore
import com.pema.clinic.shared.finance.PaymentAlertLogic
import com.pema.clinic.shared.finance.ProcedureEntry
import com.pema.clinic.shared.finance.ProcedureShare
import com.pema.clinic.shared.orders.OrdersStore
import com.pema.clinic.shared.patients.PatientState
import com.pema.clinic.shared.patients.PatientsStore
import com.pema.clinic.shared.session.Session
import com.pema.clinic.shared.session.SessionStore
import com.pema.clinic.shared.util.money
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import kotlin.test.Test
import kotlin.test.assertContains
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class SharedDomainParityTest {
    @Test
    fun vietnameseLiteralsStayUtf8() {
        assertEquals("BS. Tâm", Session().staffDoctor)
        assertEquals("BS. Tâm", Session().staffName)
        assertEquals("Chưa liên hệ", careNotContacted)
    }

    @Test
    fun catalogMapperMapsProfilesProductsAndBundledData() {
        val p = CatalogMapper.profile(
            mapOf(
                "id" to "P037",
                "name" to "Trần Minh Châu",
                "doctor" to "BS. Mai",
                "sessions" to 2,
                "total" to 6,
                "appointment" to "09:30",
                "day" to "2026-09-23",
                "group" to "d3",
                "case" to "Ảnh tiến triển · D+3",
                "tasks" to listOf(mapOf("id" to "T1", "type" to "d3", "title" to "Gửi ảnh", "status" to "open")),
            ),
        )
        assertEquals(6, p.totalSessions)
        assertEquals("d3", p.careGroup)
        assertEquals("Ảnh tiến triển · D+3", p.caseLabel)
        assertTrue(p.inCareQueue)
        assertTrue(p.hasTask("d3"))
        assertEquals("MC", p.initials)

        val outside = CatalogMapper.profile(
            mapOf(
                "id" to "P001",
                "name" to "Nguyễn Văn A",
                "doctor" to "BS. Tâm",
                "sessions" to 0,
                "total" to 4,
                "appointment" to "",
                "day" to "",
            ),
        )
        assertFalse(outside.inCareQueue)
        assertTrue(outside.tasks.isEmpty())

        val product = CatalogMapper.product(
            mapOf(
                "id" to "1",
                "code" to "SP01",
                "name" to "Kem dưỡng",
                "unit" to "Tuýp",
                "sourceType" to "Mỹ phẩm",
                "price" to 120000.0,
                "outputType" to "UNRESOLVED",
            ),
        )
        assertEquals(120000, product.price)
        assertTrue(product.needsClassification)
        assertTrue(product.matches("sp01"))
        assertEquals("1.200.000 ₫", money(1200000))

        val catalog = sampleCatalog()
        assertEquals(115, catalog.products.size)
        assertEquals(7, catalog.products.count { it.needsClassification })
        assertEquals(46, catalog.profiles.size)
        val cases = catalog.profiles.filter { it.inCareQueue }
        assertEquals(10, cases.map { it.careGroup }.toSet().size)
        for (case in cases) assertTrue(case.hasTask(case.careGroup), case.id)
    }

    @Test
    fun patientStateOrdersReceiptsAndIsolationMatchFlutter() {
        val fixture = clinicFixture()
        val catalog = fixture.catalog.catalog()
        val session = fixture.session
        val patients = fixture.patients
        val orders = fixture.orders
        val receipts = fixture.receipts

        val id = session.selectedPatientId()
        val product = catalog.products.first()
        patients.addToCart(id, product)
        assertFalse(patients.of(id).cartReady)
        assertFailsWith<IllegalStateException> { orders.save(id, approve = true) }
        patients.updateLine(id, 0) { it.copy(usage = "Hướng dẫn được bác sĩ kiểm tra") }
        assertTrue(patients.of(id).cartReady)
        orders.save(id, approve = false)
        assertFalse(orders.patientOrders(id).single().approved)
        assertTrue(patients.of(id).cart.isEmpty())
        orders.edit(id, orders.patientOrders(id).single())
        orders.save(id, approve = true)
        assertEquals(1, orders.patientOrders(id).size)
        assertTrue(orders.patientOrders(id).single().approved)
        assertEquals(orders.patientOrders(id).single().total, receipts.currentBill().total)
        receipts.settle(id, 100)
        assertEquals(100, receipts.currentBill().paid)
        session.select(1)
        assertTrue(orders.patientOrders(session.selectedPatientId()).isEmpty())
        assertEquals(0, receipts.currentPaid())

        val a = catalog.patientIds[0]
        val b = catalog.patientIds[1]
        assertTrue(orders.patientOrders(a).isNotEmpty())
        patients.addToCart(b, catalog.products.first())
        orders.save(b, approve = false)
        assertEquals(1, orders.patientOrders(a).size)
    }

    @Test
    fun mobileRoleRulesAndPatientIsolationMatchFlutter() {
        val fixture = clinicFixture()
        val catalog = fixture.catalog.catalog()
        val session = fixture.session
        val patients = fixture.patients

        session.select(36)
        val id = session.selectedPatientId()
        patients.update(id) {
            it.copy(
                note = "Clinical",
                response = "Approved reply",
                day = "2026-10-01",
                appointment = "14:00",
                acknowledged = true,
                updates = listOf("My update"),
                careNote = "PRIVATE",
                escalations = listOf("Internal"),
                editingOrder = "Draft",
            )
        }
        patients.addToCart(id, catalog.products.first())
        session.select(37)
        fun current(): PatientState = patients.of(session.selectedPatientId())
        assertEquals("", current().note)
        assertEquals("", current().response)
        assertEquals("", current().day)
        assertFalse(current().acknowledged)
        assertTrue(current().updates.isEmpty())
        assertTrue(current().cart.isEmpty())
        assertNull(current().editingOrder)
        assertEquals("", current().careNote)
        assertTrue(current().escalations.isEmpty())

        session.select(36)
        assertEquals("Clinical", current().note)
        assertEquals("2026-10-01", current().day)
        assertEquals(1, current().cart.size)
        session.enterCare()
        assertEquals(0, session.state.value.selected)
        session.select(38)
        session.enterStaff("owner", "BS. Tâm")
        assertEquals(36, session.state.value.selected)

        val care = Session(staffRole = "care")
        assertFalse(care.allows(Routes.Consultation))
        assertFalse(care.allows("Thu ngân"))
        assertTrue(care.allows("Chăm sóc khách hàng"))
        assertTrue(care.allows(Routes.Booking))
        assertFalse(care.allows(Routes.Patient360))

        val accountant = Session(staffRole = "accountant")
        assertTrue(accountant.allows(Routes.Cashier))
        assertTrue(accountant.allows(Routes.Invoices))
        assertTrue(accountant.allows(Routes.Guide))
        assertFalse(accountant.allows(Routes.Finance))

        val mai = Session(staffRole = "doctor", staffDoctor = "BS. Mai")
        assertFalse(mai.owns(catalog.profiles[36]))
        assertTrue(mai.owns(catalog.profiles[37]))
        assertFalse(mai.billing)
        assertFalse(mai.allows(Routes.Cashier))
        assertFalse(mai.allows(Routes.Resources))
        assertFalse(mai.allows(Routes.Services))
        assertFalse(mai.allows(Routes.CustomerCare))
        assertTrue(mai.allows(Routes.QuickOrder))

        val careMode = Session(careMode = true)
        assertTrue(careMode.allows(Routes.MyAppointments))
        assertTrue(careMode.allows(Routes.HomeCare))
        assertTrue(careMode.allows(Routes.Privacy))
        assertFalse(careMode.allows(Routes.Patient360))

        val doctorStore = clinicFixture().session
        doctorStore.select(36)
        doctorStore.enterStaff("doctor", "BS. Mai")
        assertEquals(1, doctorStore.state.value.selected)
        assertEquals("BS. Mai", doctorStore.selectedProfile().doctor)
    }

    @Test
    fun careAndReviewQueuesMatchProviderLogic() = runTest {
        val fixture = clinicFixture(backgroundScope)
        val catalog = fixture.catalog.catalog()
        val care = fixture.careQueue
        val review = fixture.reviewQueue
        val patients = fixture.patients
        val session = fixture.session
        runCurrent()

        assertEquals("Ảnh tiến triển · D+3", careGroups.getValue("d3"))
        assertEquals(10, care.cases().size)
        assertEquals(10, care.rows(CareQueueFilter()).size)
        assertEquals("10 khách", care.rowCountLabel(10))
        assertEquals("Danh sách cần chăm sóc", care.titleForBucket(careNotContacted))
        assertEquals(1, care.groupCount("d3"))
        assertEquals(listOf("Trần Minh Châu"), care.rows(CareQueueFilter(group = "d3")).map { it.name })
        assertEquals(listOf("Trần Minh Châu"), care.rows(CareQueueFilter(query = "trần")).map { it.name })

        var notified = 0
        backgroundScope.launch { care.state.drop(1).collect { notified++ } }
        runCurrent()
        val first = care.cases().first()
        patients.addToCart(first.profile.id, catalog.products.first())
        runCurrent()
        assertEquals(0, notified)
        patients.update(first.profile.id) { it.copy(careStatus = "Đã liên hệ") }
        runCurrent()
        assertEquals("Đã liên hệ", care.cases().first().status)
        assertEquals(1, notified)
        assertEquals(1, care.bucketCount("Đã liên hệ"))

        session.enterStaff("doctor", "BS. Mai")
        runCurrent()
        var queue = review.profiles()
        assertTrue(queue.all { it.doctor == "BS. Mai" })
        val quiet = catalog.profiles.first { it.doctor == "BS. Mai" && it !in queue }
        patients.update(quiet.id) { it.copy(updates = listOf("Da đỡ đỏ")) }
        runCurrent()
        queue = review.profiles()
        assertContains(queue, quiet)
    }

    @Test
    fun financeMapperAndEntryMappingMatchFlutter() {
        val owner = FinanceMapper.snapshot(fixture())
        assertTrue(owner.periodOpen)
        assertEquals(1200000, owner.summary.collected)
        assertEquals("BS. Mai", owner.doctorName("D1"))
        assertEquals(2400000, owner.revenueOf("D0"))
        assertEquals(20.0, owner.rows.single().ratePercent)
        assertEquals(1200000, owner.receivable.single().due)
        assertEquals(1, owner.unread)
        assertEquals("2026-09-22 10:00", owner.notifications.single().shortTime)
        assertEquals(FinanceMapper.snapshot(fixture()), FinanceMapper.snapshot(fixture()))

        val doctor = FinanceMapper.snapshot(fixture(role = "doctor"))
        assertNull(doctor.summary.collected)
        assertNull(doctor.summary.debt)
        assertTrue(doctor.invoices.isEmpty())

        val body = FinanceMapper.entry(
            ProcedureEntry(
                patient = "P001",
                invoice = "",
                service = "S0",
                date = "2026-09-22",
                listPrice = 2500000,
                discount = 100000,
                note = "Hoàn tất",
                people = listOf(
                    ProcedureShare(doctor = "D0", share = 7000, rate = 2000),
                    ProcedureShare(doctor = "D1", share = 3000, rate = 1000),
                ),
            ),
        )
        assertEquals(2500000, body["list"])
        assertEquals(
            listOf(
                mapOf("doctor" to "D0", "share" to 7000, "rate" to 2000),
                mapOf("doctor" to "D1", "share" to 3000, "rate" to 1000),
            ),
            body["people"],
        )
    }

    @Test
    fun financeStoreRolePollingCommandsAndPaymentAlertsMatchFlutter() = runTest {
        val repository = FakeFinanceRepository(stateFactory = { actor -> FinanceMapper.snapshot(fixture(role = actor.role)) })
        val store = FinanceStore(repository, backgroundScope, initialState = FinanceState(month = "2026-09"))

        store.refresh()
        assertEquals(1, store.state.value.unread)
        store.select("doctor:D1")
        assertNull(store.state.value.data)
        store.refresh()
        advanceUntilIdle()
        assertEquals(0, store.state.value.unread)
        assertTrue(store.state.value.data!!.invoices.isEmpty())
        assertNull(store.state.value.data!!.summary.collected)

        var notified = 0
        val stable = FinanceStore(repository, backgroundScope, initialState = FinanceState(month = "2026-09"))
        backgroundScope.launch { stable.state.drop(1).collect { notified++ } }
        runCurrent()
        stable.refresh()
        runCurrent()
        assertEquals(1, notified)
        stable.refresh()
        stable.refresh()
        runCurrent()
        assertEquals(1, notified)

        val failing = FinanceStore(
            FakeFinanceRepository(stateFactory = { FinanceMapper.snapshot(fixture()) }, commandError = Exception("Số thu vượt công nợ")),
            backgroundScope,
            initialState = FinanceState(month = "2026-09"),
        )
        assertFalse(failing.recordPayment(key = "k", invoice = "FIN-1", amount = 9999999))
        assertContains(failing.state.value.error, "vượt công nợ")
        assertNull(failing.state.value.data)
        assertFalse(failing.state.value.sending)

        val previous = FinanceState(month = "2026-09", data = FinanceMapper.snapshot(fixture(payments = 1)))
        val next = FinanceState(month = "2026-09", data = FinanceMapper.snapshot(fixture(payments = 2)))
        assertTrue(PaymentAlertLogic.shouldNotify(true, Session(), previous, next))
        assertFalse(PaymentAlertLogic.shouldNotify(false, Session(), previous, next))
        assertFalse(PaymentAlertLogic.shouldNotify(true, Session(careMode = true), previous, next))
        assertFalse(PaymentAlertLogic.shouldNotify(true, Session(staffRole = "accountant"), previous, next))
        assertFalse(PaymentAlertLogic.shouldNotify(true, Session(), null, next))
        assertEquals("Có thanh toán mới tại phòng khám", PaymentAlertLogic.message)
        assertEquals(3, PaymentAlertLogic.financeTab)
    }

    private fun clinicFixture(scope: kotlinx.coroutines.CoroutineScope? = null): ClinicFixture {
        val catalog = MutableCatalogRepository(sampleCatalog())
        val session = SessionStore(catalog)
        val patients = PatientsStore(catalog)
        val orders = OrdersStore(patients, catalog)
        val receipts = ReceiptsStore(session, orders)
        val actualScope = scope ?: kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Job())
        val care = CareQueue(catalog, patients, actualScope)
        val review = ReviewQueue(catalog, patients, session, actualScope)
        return ClinicFixture(catalog, session, patients, orders, receipts, care, review)
    }
}

private data class ClinicFixture(
    val catalog: MutableCatalogRepository,
    val session: SessionStore,
    val patients: PatientsStore,
    val orders: OrdersStore,
    val receipts: ReceiptsStore,
    val careQueue: CareQueue,
    val reviewQueue: ReviewQueue,
)

private class FakeFinanceRepository(
    private val stateFactory: (FinanceActor) -> FinanceSnapshot,
    private val commandError: Throwable? = null,
) : FinanceRepository {
    val commands = mutableListOf<Pair<String, FinanceActor>>()

    override suspend fun getState(month: String, actor: FinanceActor): FinanceSnapshot = stateFactory(actor)
    override suspend fun approveEntry(id: String, actor: FinanceActor) = command("approve", actor)
    override suspend fun voidEntry(id: String, reason: String, actor: FinanceActor) = command("void", actor)
    override suspend fun recordEntry(entry: ProcedureEntry, actor: FinanceActor) = command("entry", actor)
    override suspend fun recordPayment(key: String, invoice: String, amount: Int, method: String, actor: FinanceActor) = command("payment", actor)
    override suspend fun closePeriod(month: String, actor: FinanceActor) = command("close", actor)
    override suspend fun markPeriodPaid(month: String, reference: String, actor: FinanceActor) = command("paid", actor)
    override suspend fun updateRate(service: String, rate: Int, basis: String, actor: FinanceActor) = command("rate", actor)
    override suspend fun markNotificationRead(id: String, actor: FinanceActor) = command("read", actor)

    private fun command(name: String, actor: FinanceActor) {
        commandError?.let { throw it }
        commands += name to actor
    }
}

private fun fixture(role: String = "owner", payments: Int? = null): JsonObject = buildJsonObject {
    put("today", "2026-09-22")
    put("month", "2026-09")
    put("role", role)
    put("doctor", "D0")
    putJsonObject("summary") {
        put("revenue", 2400000)
        put("fee", 480000)
        put("pending", 0)
        if (role != "doctor") {
            put("collected", 1200000)
            put("debt", 1200000)
        }
    }
    putJsonObject("period") { put("status", "open") }
    putJsonArray("doctors") {
        add(buildJsonObject { put("id", "D0"); put("name", "BS. Tâm") })
        add(buildJsonObject { put("id", "D1"); put("name", "BS. Mai") })
    }
    putJsonArray("services") {
        add(
            buildJsonObject {
                put("id", "S0")
                put("name", "Laser theo chỉ định")
                put("price", 2500000)
                put("rate", 2000)
                put("basis", "net")
                put("version", 1)
            },
        )
    }
    putJsonArray("rows") {
        add(
            buildJsonObject {
                put("id", "TT-1")
                put("date", "2026-09-22")
                put("patient", "P001")
                put("service", "Laser theo chỉ định")
                put("doctor", "D0")
                put("status", "approved")
                put("basis", "net")
                put("base", 2400000)
                put("rate", 2000)
                put("share", 10000)
                put("revenue", 2400000)
                put("fee", 480000)
            },
        )
    }
    putJsonArray("invoices") {
        if (role != "doctor") {
            add(
                buildJsonObject {
                    put("id", "FIN-1")
                    put("patient", "P001")
                    put("source", "finance")
                    put("amount", 2400000)
                    put("received", 1200000)
                },
            )
        }
    }
    putJsonArray("notifications") {
        val count = payments ?: if (role == "owner") 1 else 0
        repeat(count) { index ->
            add(
                buildJsonObject {
                    put("id", "PT-$index")
                    put("title", "Đã nhận thanh toán")
                    put("body", if (payments == null) "P001 · 1.200.000 đ · Tiền mặt" else "P001")
                    put("read", false)
                    put("at", "2026-09-22T10:00:00+07:00")
                },
            )
        }
    }
}
