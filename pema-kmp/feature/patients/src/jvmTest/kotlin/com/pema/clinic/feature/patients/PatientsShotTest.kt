package com.pema.clinic.feature.patients

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.common.AppNavigator
import com.pema.clinic.core.hardware.FakePlatformServices
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.core.ui.widgets.PemaBottomNav
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaMainTopBar
import com.pema.clinic.core.ui.widgets.PemaNavItem
import com.pema.clinic.core.ui.widgets.PemaScaffold
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.billing.ReceiptsStore
import com.pema.clinic.shared.care.CareQueue
import com.pema.clinic.shared.care.ReviewQueue
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import com.pema.clinic.shared.catalog.sampleCatalog
import com.pema.clinic.shared.finance.FinanceActor
import com.pema.clinic.shared.finance.FinanceRepository
import com.pema.clinic.shared.finance.FinanceSnapshot
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.FinanceStore
import com.pema.clinic.shared.finance.FinanceSummary
import com.pema.clinic.shared.finance.ProcedureEntry
import com.pema.clinic.shared.orders.OrdersStore
import com.pema.clinic.shared.patients.PatientsStore
import com.pema.clinic.shared.session.SessionStore
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain

@OptIn(ExperimentalCoroutinesApi::class)
class PatientsShotTest {
    private val mainDispatcher = UnconfinedTestDispatcher()

    @BeforeTest
    fun setMainDispatcher() {
        Dispatchers.setMain(mainDispatcher)
    }

    @AfterTest
    fun resetMainDispatcher() {
        Dispatchers.resetMain()
    }

    @Test
    fun a3OwnerPatientSearch() {
        val deps = deps()
        shotVsCanvas("A3") {
            PatientSearchWorkspace(
                deps = deps,
                roleLabel = "Clinic",
                unread = 1,
                navItems = ownerNav,
                selectedIndex = 2,
                headingTitle = "Hồ sơ người bệnh",
                headingSub = "${deps.catalogRepository.catalog().profiles.size} hồ sơ tổng hợp · Patient 360",
            )
        }
    }

    @Test
    fun b2DoctorPatientSearch() {
        val deps = deps(role = "doctor", name = "BS. Tâm")
        shotVsCanvas("B2") {
            PatientSearchWorkspace(
                deps = deps,
                roleLabel = "Bác sĩ",
                navItems = staffNav,
                selectedIndex = 1,
                headingTitle = "Hồ sơ phụ trách",
                headingSub = "BS. Tâm",
            )
        }
    }

    @Test
    fun c5CarePatientSearch() {
        val deps = deps(role = "care", name = "Mai Anh")
        shotVsCanvas("C5") {
            PatientSearchWorkspace(
                deps = deps,
                roleLabel = "CSKH",
                navItems = staffNav,
                selectedIndex = 1,
                headingTitle = "Hồ sơ phụ trách",
                headingSub = "Mai Anh",
            )
        }
    }

    @Test
    fun d2AccountantPatientSearch() {
        val deps = deps(role = "accountant", name = "Kế toán")
        shotVsCanvas("D2") {
            PatientSearchWorkspace(
                deps = deps,
                roleLabel = "Kế toán",
                navItems = staffNav,
                selectedIndex = 1,
                headingTitle = "Hồ sơ phụ trách",
                headingSub = "Kế toán",
            )
        }
    }

    @Test fun f1Patient360() { shotVsCanvas("F1") { WithBack { Patient360Route(deps()) } } }
    @Test fun f2Consultation() { shotVsCanvas("F2") { WithBack { ConsultationRoute(deps()) } } }
    @Test fun f3TreatmentSession() { shotVsCanvas("F3") { WithBack { TreatmentSessionRoute(deps()) } } }
    @Test fun f15AskPema() { shotVsCanvas("F15") { WithBack { AskPemaRoute(deps()) } } }
    @Test fun g4TreatmentPlan() { shotVsCanvas("G4") { WithBack { TreatmentPlanRoute(deps()) } } }
    @Test fun g5ProgressPhotos() { shotVsCanvas("G5") { WithBack { ProgressPhotosRoute(deps()) } } }

    private val ownerNav = listOf(
        PemaNavItem("Hôm nay", "space_dashboard"),
        PemaNavItem("Lịch hẹn", "calendar_month"),
        PemaNavItem("Hồ sơ", "group"),
        PemaNavItem("Theo dõi", "inbox"),
        PemaNavItem("Thêm", "grid_view"),
    )

    private val staffNav = listOf(
        PemaNavItem("Công việc", "work"),
        PemaNavItem("Hồ sơ mẫu", "group"),
    )

    @Composable
    private fun WithBack(content: @Composable () -> Unit) {
        CompositionLocalProvider(LocalOnBack provides {}, content = content)
    }

    @Composable
    private fun PatientSearchWorkspace(
        deps: FeatureDeps,
        roleLabel: String,
        navItems: List<PemaNavItem>,
        selectedIndex: Int,
        headingTitle: String,
        headingSub: String,
        unread: Int? = null,
    ) {
        PemaScaffold(
            topBar = { PemaMainTopBar(roleLabel, onRoleClick = {}, unread = unread) },
            bottomBar = { PemaBottomNav(navItems, selectedIndex, onSelect = {}) },
        ) { inner ->
            Box(Modifier.fillMaxSize().padding(inner), contentAlignment = Alignment.TopCenter) {
                Column(
                    Modifier
                        .widthIn(max = 720.dp)
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(start = 20.dp, top = 8.dp, end = 20.dp, bottom = 24.dp),
                ) {
                    PemaHeading(headingTitle, headingSub)
                    PatientSearch(deps = deps, onOpen = {})
                }
            }
        }
    }

    private fun deps(role: String = "owner", name: String = "BS. Tâm"): FeatureDeps {
        val scope = CoroutineScope(SupervisorJob())
        val catalog = MutableCatalogRepository(sampleCatalog())
        val session = SessionStore(catalog)
        if (role != "owner") session.enterStaff(role, name)
        val patients = PatientsStore(catalog)
        val firstId = catalog.catalog().patientIds.first()
        patients.update(firstId) { it.copy(updates = listOf("Da hơi đỏ nhẹ vùng má sau một ngày, không ngứa.")) }
        val orders = OrdersStore(patients, catalog)
        val receipts = ReceiptsStore(session, orders)
        val careQueue = CareQueue(catalog, patients, scope)
        val reviewQueue = ReviewQueue(catalog, patients, session, scope)
        val financeRole = if (role == "doctor") "doctor" else role
        val financeStore = FinanceStore(
            repository = ShotFinanceRepository(),
            scope = scope,
            initialState = FinanceState(
                month = "2026-09",
                role = financeRole,
                doctor = if (name == "BS. Mai") "D1" else "D0",
                data = financeSnapshot(),
            ),
        )
        return FeatureDeps(
            navigator = NoopNavigator,
            platform = FakePlatformServices(),
            catalogRepository = catalog,
            sessionStore = session,
            patientsStore = patients,
            ordersStore = orders,
            receiptsStore = receipts,
            careQueue = careQueue,
            reviewQueue = reviewQueue,
            financeStore = financeStore,
        )
    }

    private object NoopNavigator : AppNavigator {
        override fun go(route: String) = Unit
        override fun back() = Unit
    }

    private class ShotFinanceRepository : FinanceRepository {
        override suspend fun getState(month: String, actor: FinanceActor): FinanceSnapshot = financeSnapshot()
        override suspend fun approveEntry(id: String, actor: FinanceActor) = Unit
        override suspend fun voidEntry(id: String, reason: String, actor: FinanceActor) = Unit
        override suspend fun recordEntry(entry: ProcedureEntry, actor: FinanceActor) = Unit
        override suspend fun recordPayment(key: String, invoice: String, amount: Int, method: String, actor: FinanceActor) = Unit
        override suspend fun closePeriod(month: String, actor: FinanceActor) = Unit
        override suspend fun markPeriodPaid(month: String, reference: String, actor: FinanceActor) = Unit
        override suspend fun updateRate(service: String, rate: Int, basis: String, actor: FinanceActor) = Unit
        override suspend fun markNotificationRead(id: String, actor: FinanceActor) = Unit
    }
}

private fun financeSnapshot(): FinanceSnapshot = FinanceSnapshot(
    month = "2026-09",
    today = "2026-09-22",
    periodStatus = "open",
    summary = FinanceSummary(revenue = 186_400_000, fee = 18_640_000, pending = 0, collected = 152_000_000, debt = 34_400_000),
)
