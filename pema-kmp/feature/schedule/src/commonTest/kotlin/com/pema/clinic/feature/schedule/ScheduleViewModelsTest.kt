package com.pema.clinic.feature.schedule

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
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ScheduleViewModelsTest {
    @Test
    fun bookingKeepsFlutterSlotsAndBlocksNineOClock() {
        val fixture = scheduleFixture()
        val viewModel = BookingViewModel(fixture.deps)

        viewModel.chooseSlot(blockedBookingSlot)
        val id = fixture.sessionStore.selectedPatientId()
        assertEquals("08:00", fixture.patientsStore.of(id).appointment)

        viewModel.chooseSlot("10:30")
        viewModel.chooseDay("22/9/2026")

        assertEquals("10:30", fixture.patientsStore.of(id).appointment)
        assertEquals("22/9/2026", fixture.patientsStore.of(id).day)
        assertEquals(listOf("09:00", "10:30", "11:00", "14:00", "15:30"), bookingSlots)
        assertEquals("22/9/2026", formatPickedDayForTest())
    }

    @Test
    fun bookingConfirmMarksPatientConfirmedShowsFlutterSnackAndGoesBack() {
        val fixture = scheduleFixture()
        val viewModel = BookingViewModel(fixture.deps)

        viewModel.chooseSlot("14:00")
        val message = viewModel.confirm()

        val id = fixture.sessionStore.selectedPatientId()
        assertTrue(fixture.patientsStore.of(id).confirmed)
        assertEquals(1, fixture.navigator.backCount)
        assertEquals("Đã lưu lịch 14:00 · 2026-09-20", message)
    }

    @Test
    fun appointmentDetailUsesRouteTitleAndUpdatesAttendance() {
        val fixture = scheduleFixture()
        val viewModel = AppointmentViewModel(fixture.deps, Routes.MyAppointments)

        assertEquals("Lịch của tôi", viewModel.title)
        assertFalse(viewModel.state().confirmed)

        viewModel.confirmAttendance()

        val id = fixture.sessionStore.selectedPatientId()
        assertTrue(fixture.patientsStore.of(id).confirmed)
        assertEquals("Đã xác nhận", viewModel.state().confirmText)
    }

    @Test
    fun appointmentDetailNavigatesToBookingAndPatient360ForStaff() {
        val fixture = scheduleFixture()
        val viewModel = AppointmentViewModel(fixture.deps, Routes.AppointmentDetail)

        assertTrue(viewModel.state().showClinicActions)
        viewModel.reschedule()
        viewModel.openPatient360()

        assertEquals(listOf(Routes.Booking, Routes.Patient360), fixture.navigator.opened)
    }

    @Test
    fun myAppointmentsOnlyShowsAttendanceInCareMode() {
        val fixture = scheduleFixture()
        fixture.sessionStore.enterCare()
        val viewModel = AppointmentViewModel(fixture.deps, Routes.MyAppointments)
        val state = viewModel.state()

        assertFalse(state.showClinicActions)
        assertEquals("${state.appointment} · ${state.day}", state.heroTitle)
        assertEquals("Lịch của tôi", state.title)
    }

    @Test
    fun servicesAndResourcesMatchFlutterReferenceRows() {
        assertEquals(
            listOf(
                "Tái khám & đánh giá|300.000 ₫ · 30 phút",
                "Tư vấn da liễu|500.000 ₫ · 45 phút",
                "Laser theo chỉ định|2.500.000 ₫ · 45 + 15 phút",
                "Chăm sóc theo chỉ định|1.200.000 ₫ · 45 + 15 phút",
            ),
            scheduleServices.map { "${it.name}|${it.description}" },
        )
        assertEquals(
            listOf("BS. Tâm", "BS. Mai", "BS. An", "BS. Lan"),
            scheduleResources.map { it.name },
        )
    }
}

private data class ScheduleFixture(
    val deps: FeatureDeps,
    val navigator: RecordingNavigator,
    val sessionStore: SessionStore,
    val patientsStore: PatientsStore,
)

private fun scheduleFixture(): ScheduleFixture {
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
    return ScheduleFixture(deps, navigator, sessionStore, patientsStore)
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

private fun formatPickedDayForTest(): String = formatPickedDay(bookingInitialDateMillisForTest)

private val bookingInitialDateMillisForTest = LocalDateForTest.millis20260922

private object LocalDateForTest {
    val millis20260922: Long = LocalDate(2026, 9, 22)
        .atStartOfDayIn(TimeZone.UTC)
        .toEpochMilliseconds()
}
