package com.pema.clinic.feature.finance

import com.pema.clinic.shared.finance.FinanceActor
import com.pema.clinic.shared.finance.FinanceDoctor
import com.pema.clinic.shared.finance.FinanceInvoice
import com.pema.clinic.shared.finance.FinanceRepository
import com.pema.clinic.shared.finance.FinanceSnapshot
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.FinanceStore
import com.pema.clinic.shared.finance.FinanceSummary
import com.pema.clinic.shared.finance.PaymentAlertLogic
import com.pema.clinic.shared.finance.PaymentNotification
import com.pema.clinic.shared.finance.ProcedureEntry
import com.pema.clinic.shared.finance.ProcedureRow
import com.pema.clinic.shared.finance.ProcedureService
import com.pema.clinic.shared.session.Session
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest

class FinanceRulesTest {
    @Test
    fun roleSelectionClearsPrivateDataAndReceivesNotifications() = runTest {
        val repository = FakeFinanceRepository(stateFactory = { actor -> financeFixture(role = actor.role) })
        val store = FinanceStore(repository, backgroundScope, initialState = FinanceState(month = "2026-09"))

        store.refresh()
        assertEquals(1, store.state.value.unread)

        store.select("doctor:D1")
        assertNull(store.state.value.data)
        store.refresh()
        advanceUntilIdle()

        val doctor = assertNotNull(store.state.value.data)
        assertEquals(0, store.state.value.unread)
        assertTrue(doctor.invoices.isEmpty())
        assertNull(doctor.summary.collected)
    }

    @Test
    fun identicalPollResponseDoesNotNotifyFinanceWatchers() = runTest {
        val store = FinanceStore(
            FakeFinanceRepository(stateFactory = { financeFixture() }),
            backgroundScope,
            initialState = FinanceState(month = "2026-09"),
        )
        var notified = 0
        backgroundScope.launch { store.state.drop(1).collect { notified++ } }
        runCurrent()

        store.refresh()
        runCurrent()
        assertEquals(1, notified)
        store.refresh()
        store.refresh()
        runCurrent()
        assertEquals(1, notified)
    }

    @Test
    fun failedPaymentRetainsServerErrorAndDoesNotFabricateSuccess() = runTest {
        val store = FinanceStore(
            FakeFinanceRepository(stateFactory = { financeFixture() }, commandError = Exception("Số thu vượt công nợ")),
            backgroundScope,
            initialState = FinanceState(month = "2026-09"),
        )

        assertFalse(store.recordPayment(key = "k", invoice = "FIN-1", amount = 9_999_999))
        assertTrue(store.state.value.error.contains("vượt công nợ"))
        assertNull(store.state.value.data)
        assertFalse(store.state.value.sending)
    }

    @Test
    fun paymentAlertRulesMatchFlutterConditions() {
        val previous = FinanceState(month = "2026-09", data = financeFixture(payments = 1))
        val next = FinanceState(month = "2026-09", data = financeFixture(payments = 2))

        assertTrue(PaymentAlertLogic.shouldNotify(true, Session(), previous, next))
        assertFalse(PaymentAlertLogic.shouldNotify(false, Session(), previous, next))
        assertFalse(PaymentAlertLogic.shouldNotify(true, Session(careMode = true), previous, next))
        assertFalse(PaymentAlertLogic.shouldNotify(true, Session(staffRole = "accountant"), previous, next))
        assertFalse(PaymentAlertLogic.shouldNotify(true, Session(), null, next))
        assertEquals("Có thanh toán mới tại phòng khám", PaymentAlertLogic.message)
        assertEquals("Xem", PaymentAlertLogic.actionLabel)
        assertEquals(3, PaymentAlertLogic.financeTab)
    }

    @Test
    fun doctorOverviewHidesOwnerOnlyCashDebtTeamAndReceivables() {
        val ownerSnapshot = financeFixture(role = "owner")
        val doctorSnapshot = financeFixture(role = "doctor")
        val ownerLines = overviewLines(FinanceState(month = "2026-09", role = "owner"), ownerSnapshot).map { it.label }
        val doctorLines = overviewLines(FinanceState(month = "2026-09", role = "doctor"), doctorSnapshot).map { it.label }

        assertTrue("Thực thu trong tháng" in ownerLines)
        assertTrue("Công nợ hiện tại" in ownerLines)
        assertFalse("Thực thu trong tháng" in doctorLines)
        assertFalse("Công nợ hiện tại" in doctorLines)
        assertTrue(doctorSnapshot.receivable.isEmpty())
        assertNull(doctorSnapshot.summary.debt)
    }

    @Test
    fun procedureFormSplitsRevenueWeightBetweenMainDoctorAndAssistant() {
        val entry: ProcedureEntry = buildProcedureEntry(
            ProcedureFormValues(
                patient = "P001",
                invoice = "",
                service = "S0",
                date = "2026-09-22",
                gross = "2500000",
                discount = "100000",
                doctor = "D0",
                assistant = "D1",
                share = "70",
                rate = "20",
                rate2 = "10",
                note = "Hoàn tất",
            ),
        )

        assertEquals(2_500_000, entry.listPrice)
        assertEquals(
            listOf("D0" to 7_000, "D1" to 3_000),
            entry.people.map { it.doctor to it.share },
        )
        assertEquals(listOf(2_000, 1_000), entry.people.map { it.rate })
        assertNull(validateProcedureForm(
            ProcedureFormValues("P001", "", "S0", "2026-09-22", "1", "0", "D0", "", "100", "10", "0", "X"),
        ))
        assertEquals(
            "Cần nhập trường này",
            validateProcedureForm(
                ProcedureFormValues("P001", "", "S0", "2026-09-22", "1", "0", "D0", "", "100", "10", "0", ""),
            ),
        )
    }
}

internal fun financeFixture(
    role: String = "owner",
    payments: Int? = null,
    periodStatus: String = "open",
): FinanceSnapshot {
    val owner = role != "doctor"
    val paymentCount = payments ?: if (role == "owner") 1 else 0
    return FinanceSnapshot(
        month = "2026-09",
        today = "2026-09-22",
        periodStatus = periodStatus,
        summary = FinanceSummary(
            revenue = if (owner) 186_400_000 else 84_200_000,
            fee = if (owner) 18_640_000 else 8_170_000,
            pending = if (owner) 3_200_000 else 250_000,
            collected = if (owner) 152_000_000 else null,
            debt = if (owner) 34_400_000 else null,
        ),
        doctors = listOf(
            FinanceDoctor("D0", "BS. Tâm"),
            FinanceDoctor("D1", "BS. Mai"),
            FinanceDoctor("D2", "BS. An"),
            FinanceDoctor("D3", "BS. Lan"),
        ),
        services = listOf(
            ProcedureService("S0", "Laser theo chỉ định", 2_500_000, 1_000, "net", 3),
            ProcedureService("S1", "Chăm sóc theo chỉ định", 1_200_000, 800, "net", 1),
            ProcedureService("S2", "Tư vấn da liễu", 500_000, 500, "list", 2),
            ProcedureService("S3", "Tái khám & đánh giá", 300_000, 500, "collected", 1),
        ),
        rows = listOf(
            ProcedureRow("TT-1", "2026-09-21", "P001", "Laser theo chỉ định", "D0", "pending", 2_500_000, 1_000, 2_500_000, 250_000),
            ProcedureRow("TT-2", "2026-09-18", "P003", "Chăm sóc theo chỉ định", "D0", "approved", 1_200_000, 800, 1_200_000, 96_000),
            ProcedureRow("TT-3", "2026-09-15", "P002", "Tư vấn da liễu", "D1", "approved", 500_000, 500, 500_000, 25_000),
            ProcedureRow("TT-4", "2026-09-12", "P004", "Laser theo chỉ định", "D2", "void", 2_250_000, 1_000, 2_250_000, 225_000),
        ),
        invoices = if (owner) {
            listOf(
                FinanceInvoice("HD-2609-014", "P001", "finance", 5_000_000, 2_500_000),
                FinanceInvoice("HD-2609-011", "P005", "finance", 2_400_000, 1_200_000),
                FinanceInvoice("WEB-001", "P009", "web", 900_000, 0),
            )
        } else {
            emptyList()
        },
        notifications = List(paymentCount) { index ->
            PaymentNotification(
                id = "PT-$index",
                title = if (index == 0) "Đã thu 1.200.000 ₫" else "Đã thu 300.000 ₫",
                body = if (index == 0) "Kế toán thu tiền mặt · P005 · HD-2609-011" else "Kế toán thu tiền mặt · P011 · HD-2609-009",
                read = false,
                at = if (index == 0) "2026-09-22T09:41:00+07:00" else "2026-09-21T16:05:00+07:00",
            )
        },
    )
}

private class FakeFinanceRepository(
    private val stateFactory: (FinanceActor) -> FinanceSnapshot,
    private val commandError: Throwable? = null,
) : FinanceRepository {
    override suspend fun getState(month: String, actor: FinanceActor): FinanceSnapshot = stateFactory(actor)
    override suspend fun approveEntry(id: String, actor: FinanceActor) = command()
    override suspend fun voidEntry(id: String, reason: String, actor: FinanceActor) = command()
    override suspend fun recordEntry(entry: ProcedureEntry, actor: FinanceActor) = command()
    override suspend fun recordPayment(key: String, invoice: String, amount: Int, method: String, actor: FinanceActor) = command()
    override suspend fun closePeriod(month: String, actor: FinanceActor) = command()
    override suspend fun markPeriodPaid(month: String, reference: String, actor: FinanceActor) = command()
    override suspend fun updateRate(service: String, rate: Int, basis: String, actor: FinanceActor) = command()
    override suspend fun markNotificationRead(id: String, actor: FinanceActor) = command()

    private fun command() {
        commandError?.let { throw it }
    }
}
