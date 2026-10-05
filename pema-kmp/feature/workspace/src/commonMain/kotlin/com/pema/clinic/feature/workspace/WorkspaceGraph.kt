package com.pema.clinic.feature.workspace

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import androidx.savedstate.read
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.Gap
import com.pema.clinic.core.ui.widgets.PemaAction
import com.pema.clinic.core.ui.widgets.PemaActions
import com.pema.clinic.core.ui.widgets.PemaBottomNav
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaHero
import com.pema.clinic.core.ui.widgets.PemaListRow
import com.pema.clinic.core.ui.widgets.PemaMainTopBar
import com.pema.clinic.core.ui.widgets.PemaMetrics
import com.pema.clinic.core.ui.widgets.PemaNavItem
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaScaffold
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.core.ui.widgets.WeekStrip
import com.pema.clinic.feature.care.CareQueue as CareQueueWidget
import com.pema.clinic.feature.patients.PatientSearchState
import com.pema.clinic.feature.patients.patientSearchItems
import com.pema.clinic.feature.patients.rememberPatientSearchState
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.catalog.Catalog
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.patients.PatientState
import com.pema.clinic.shared.session.Session
import com.pema.clinic.shared.clinic.ClinicPatient
import com.pema.clinic.shared.clinic.patientJourneyTimeline
import com.pema.clinic.shared.util.money

fun NavGraphBuilder.workspaceGraph(deps: FeatureDeps) {
    composable(Routes.Workspace) { WorkspaceRoute(deps) }
    composable(
        Routes.GuidePattern,
        arguments = listOf(navArgument("route") { type = NavType.StringType; defaultValue = Routes.titleOf(Routes.Guide) }),
    ) { entry ->
        GuideScreen(entry.arguments?.read { getStringOrNull("route") } ?: Routes.titleOf(Routes.Guide))
    }
}

@Composable
internal fun WorkspaceRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val patientsSnapshot by deps.patientsStore.state.collectAsStateWithLifecycle()
    val financeState by deps.financeStore.state.collectAsStateWithLifecycle()
    val reviewProfiles by deps.reviewQueue.state.collectAsStateWithLifecycle()
    val catalog = deps.catalogRepository.catalog()
    val selected = session.selected.coerceIn(0, catalog.profiles.lastIndex)
    val profile = catalog.profiles[selected]
    val patient = remember(patientsSnapshot, profile.id) { deps.patientsStore.of(profile.id) }
    val clinicState by deps.clinicStore.state.collectAsStateWithLifecycle()
    val clinicPatient = remember(clinicState, profile.id) { clinicState.patients.firstOrNull { it.id == profile.id } }

    // Saveable: NavHost drops plain `remember` state when a detail route is pushed on top.
    var selectedTab by rememberSaveable { mutableIntStateOf(0) }
    var careGroup by rememberSaveable { mutableStateOf("all") }
    var showAccountSheet by remember { mutableStateOf(false) }
    val tabCount = tabsFor(session).size

    LaunchedEffect(Unit) { deps.financeStore.start() }
    LaunchedEffect(session.careMode, session.staffRole, tabCount) {
        if (selectedTab >= tabCount) selectedTab = 0
    }

    fun open(route: String) {
        if (deps.sessionStore.state.value.allows(route)) deps.navigator.go(route)
    }

    fun selectAccount(account: WorkspaceAccount) {
        selectedTab = 0
        careGroup = "all"
        if (account.kind == "patient") {
            deps.sessionStore.enterCare()
        } else {
            deps.sessionStore.enterStaff(account.kind, account.name)
        }
        val next = deps.sessionStore.state.value
        if (!next.careMode && next.staffRole != "care") {
            deps.financeStore.select("${next.staffRole}:${if (next.staffDoctor == "BS. Mai") "D1" else "D0"}")
        }
        showAccountSheet = false
    }

    fun selectGroup(group: String) {
        careGroup = group
        if (group != "all") {
            val index = catalog.profiles.indexOfFirst { it.careGroup == group }
            if (index >= 0) deps.sessionStore.select(index)
        }
    }

    WorkspaceScreen(
        state = WorkspaceUiState(
            session = session,
            catalog = catalog,
            profile = profile,
            patient = patient,
            selectedTab = selectedTab,
            careGroup = careGroup,
            financeOn = true,
            financeState = financeState,
            reviewProfiles = reviewProfiles,
            showAccountSheet = false,
            clinicPatient = clinicPatient,
        ),
        deps = deps,
        callbacks = WorkspaceCallbacks(
            onTabSelected = { selectedTab = it },
            onRoleClick = { showAccountSheet = true },
            onBellClick = { deps.navigator.openFinance(3) },
            onOpen = ::open,
            onOpenFinance = deps.navigator::openFinance,
            onSelectAccount = ::selectAccount,
            onGroupSelected = ::selectGroup,
            onPatientSelected = deps.sessionStore::select,
            onJumpToTab = { selectedTab = it },
        ),
    )

    if (showAccountSheet) {
        com.pema.clinic.core.ui.widgets.PemaBottomSheet(onDismiss = { showAccountSheet = false }) {
            AccountSheetContent(onSelect = ::selectAccount)
        }
    }
}

data class WorkspaceUiState(
    val session: Session,
    val catalog: Catalog,
    val profile: PatientProfile,
    val patient: PatientState,
    val selectedTab: Int,
    val careGroup: String = "all",
    val financeOn: Boolean = true,
    val financeState: FinanceState = FinanceState(),
    val reviewProfiles: List<PatientProfile> = emptyList(),
    val showAccountSheet: Boolean = false,
    /** Web record of the same patient (Pema Care web additions: K3 timeline, clinic messages); null in Flutter-only shots. */
    val clinicPatient: ClinicPatient? = null,
)

data class WorkspaceCallbacks(
    val onTabSelected: (Int) -> Unit = {},
    val onRoleClick: () -> Unit = {},
    val onBellClick: () -> Unit = {},
    val onOpen: (String) -> Unit = {},
    val onOpenFinance: (Int) -> Unit = {},
    val onSelectAccount: (WorkspaceAccount) -> Unit = {},
    val onGroupSelected: (String) -> Unit = {},
    val onPatientSelected: (Int) -> Unit = {},
    val onJumpToTab: (Int) -> Unit = {},
)

data class WorkspaceAccount(val kind: String, val name: String, val description: String)

val workspaceAccounts = listOf(
    WorkspaceAccount("owner", "BS. Tâm", "Chủ phòng khám"),
    WorkspaceAccount("doctor", "BS. Tâm", "Bác sĩ điều trị"),
    WorkspaceAccount("doctor", "BS. Mai", "Bác sĩ điều trị"),
    WorkspaceAccount("care", "Mai Anh", "CSKH"),
    WorkspaceAccount("accountant", "Kế toán", "Đối soát & thu ngân"),
    WorkspaceAccount("patient", "Người bệnh", "Pema Care"),
)

@Composable
fun WorkspaceScreen(
    state: WorkspaceUiState,
    callbacks: WorkspaceCallbacks = WorkspaceCallbacks(),
    deps: FeatureDeps? = null,
) {
    val tabs = tabsFor(state.session)
    val selectedTab = state.selectedTab.coerceIn(0, tabs.lastIndex)
    val patientSearch = if (deps != null && showsPatientSearch(state.session, selectedTab)) rememberPatientSearchState(deps) else null
    // Lazy body: only the rows on screen are composed (the owner "Hồ sơ" tab lists all 46 profiles).
    // One saved scroll position per tab: a tab opens at its top and comes back there after a pushed route.
    val listState = rememberSaveable(state.session.careMode, state.session.staffRole, selectedTab, saver = LazyListState.Saver) {
        LazyListState()
    }
    Box(Modifier.fillMaxSize()) {
        PemaScaffold(
            topBar = {
                PemaMainTopBar(
                    roleLabel = roleLabel(state.session),
                    onRoleClick = callbacks.onRoleClick,
                    unread = if (state.financeOn && !state.session.careMode && state.session.staffRole == "owner") state.financeState.unread else null,
                    onBellClick = callbacks.onBellClick,
                )
            },
            bottomBar = {
                PemaBottomNav(
                    items = tabs,
                    selectedIndex = selectedTab,
                    onSelect = callbacks.onTabSelected,
                )
            },
        ) { inner ->
            Box(Modifier.fillMaxSize().padding(inner), contentAlignment = Alignment.TopCenter) {
                LazyColumn(
                    Modifier
                        .widthIn(max = 720.dp)
                        .fillMaxSize(),
                    state = listState,
                    contentPadding = PaddingValues(start = 20.dp, top = 8.dp, end = 20.dp, bottom = 24.dp),
                ) {
                    when {
                        state.session.careMode -> careItems(state, selectedTab, callbacks)
                        state.session.staffRole != "owner" -> staffItems(state, selectedTab, callbacks, deps, patientSearch)
                        else -> ownerItems(state, selectedTab, callbacks, patientSearch)
                    }
                }
            }
        }
        if (state.showAccountSheet) {
            AccountSheetOverlay(onSelect = callbacks.onSelectAccount)
        }
    }
}

/** One [PemaTile] row of the lazy workspace body. */
private fun LazyListScope.tile(title: String, sub: String, icon: String, onClick: (() -> Unit)?) {
    item(contentType = "tile") { PemaTile(title, sub, icon, onClick) }
}

private fun LazyListScope.ownerItems(
    state: WorkspaceUiState,
    selectedTab: Int,
    callbacks: WorkspaceCallbacks,
    patientSearch: PatientSearchState?,
) {
    when (selectedTab) {
        1 -> {
            item { PemaHeading("Điều phối lịch", "Thứ Ba, 22 tháng 9") }
            item { WeekStrip() }
            tile("BS. Tâm · Phòng khám 01", "Ca sáng 08:00–12:00", "tune") { callbacks.onOpen(Routes.Resources) }
            listOf("09:00", state.patient.appointment, "14:00").forEach { time ->
                tile(
                    time,
                    if (time == state.patient.appointment) "${state.profile.name} · Tái khám" else "Khung giờ trống",
                    "schedule",
                ) { callbacks.onOpen(Routes.AppointmentDetail) }
            }
            item { PemaPrimary("Đặt / dời lịch", onClick = { callbacks.onOpen(Routes.Booking) }) }
        }
        2 -> {
            item { PemaHeading("Hồ sơ người bệnh", "${state.catalog.profiles.size} hồ sơ tổng hợp · Patient 360") }
            patientSearchArea(patientSearch, onOpen = { callbacks.onOpen(Routes.Patient360) })
        }
        3 -> {
            item { PemaHeading("Theo dõi", "Ưu tiên phản hồi và bàn giao") }
            item { PemaNotice("${state.patient.updates.size} cập nhật · ${if (state.patient.response.isEmpty()) "1 cần phản hồi" else "Đã phản hồi"}") }
            state.patient.updates.forEach { update ->
                tile(state.profile.name, update, "chat_bubble_outline") { callbacks.onOpen(Routes.FollowUpReply) }
            }
            state.reviewProfiles
                .filterNot { it.id == state.profile.id }
                .take(3)
                .forEach { profile ->
                    tile(profile.name, "Review chăm sóc · hồ sơ phụ trách", "inbox") {
                        callbacks.onPatientSelected(state.catalog.indexOf(profile.id))
                        callbacks.onOpen(Routes.FollowUpReply)
                    }
                }
            tile("Cần gọi lại", "Hồ sơ mẫu · triệu chứng tăng", "priority_high") { callbacks.onOpen(Routes.FollowUpReply) }
        }
        4 -> {
            item { PemaHeading("Không gian làm việc", "Nghiệp vụ theo đúng hành trình Pema") }
            if (state.financeOn) {
                tile("Tài chính & tiền thủ thuật", "Chủ phòng khám · Kế toán · Bác sĩ", "account_balance_wallet") { callbacks.onOpenFinance(0) }
            }
            listOf(
                "Lên đơn nhanh" to Routes.QuickOrder,
                "Thu ngân" to Routes.Cashier,
                "Dịch vụ" to Routes.Services,
                "Bác sĩ & phòng" to Routes.Resources,
                "Ảnh tiến triển" to Routes.ProgressPhotos,
                "Ask Pema" to Routes.AskPema,
                "Hướng dẫn" to Routes.Guide,
            ).forEach { (title, route) ->
                tile(title, "Mở ${title.lowercase()}", "chevron_right") { callbacks.onOpen(route) }
            }
            item { PemaNotice("Template tương tác • dữ liệu mẫu trong phiên. Chuyển Clinic/Care ở góc trên để duyệt bàn giao.") }
            webOperationsItems(state.session, callbacks)
        }
        else -> {
            item { PemaHeading("Chào buổi sáng, BS. Tâm", "Thứ Ba · 22 tháng 09, 2026") }
            item {
                Column {
                    PemaHero("Một ngày chăm sóc\ntrọn vẹn hơn.", "${state.patient.updates.size} phản hồi cần theo dõi", "wb_sunny")
                    Spacer(Modifier.height(16.dp))
                }
            }
            item { PemaMetrics("12" to "Lịch hôm nay", (if (state.patient.checkedIn) "04" else "03") to "Đang chờ") }
            if (state.financeOn) {
                item(contentType = "tile") { FinanceSummaryTile(state.financeState, onTap = { callbacks.onOpenFinance(0) }) }
            }
            item { PemaSection("Bắt đầu nhanh") }
            item {
                PemaActions(
                    listOf(
                        PemaAction("Lên đơn", "note_add") { callbacks.onOpen(Routes.QuickOrder) },
                        PemaAction("Đặt lịch", "calendar_month") { callbacks.onOpen(Routes.Booking) },
                        PemaAction("Thu ngân", "payments") { callbacks.onOpen(Routes.Cashier) },
                    ),
                )
            }
            item { PemaSection("Lượt khám tiếp theo") }
            tile(
                state.profile.name,
                "${state.patient.appointment} · ${if (state.patient.checkedIn) "Đã check-in" else "Chờ tiếp nhận"} · Tái khám",
                "person",
            ) { callbacks.onOpen(Routes.Patient360) }
            tile("Theo dõi sau điều trị", "Xem ảnh và phản hồi từ người bệnh", "inbox") { callbacks.onJumpToTab(3) }
        }
    }
}

private fun LazyListScope.staffItems(
    state: WorkspaceUiState,
    selectedTab: Int,
    callbacks: WorkspaceCallbacks,
    deps: FeatureDeps?,
    patientSearch: PatientSearchState?,
) {
    if (selectedTab == 1) {
        item { PemaHeading("Hồ sơ phụ trách", state.session.staffName) }
        patientSearchArea(
            patientSearch,
            onOpen = {
                callbacks.onOpen(
                    when (state.session.staffRole) {
                        "care" -> Routes.CustomerCare
                        "accountant" -> Routes.Invoices
                        else -> Routes.Patient360
                    },
                )
            },
        )
        return
    }

    when (state.session.staffRole) {
        "accountant" -> {
            item { PemaHeading("Đối soát & thu ngân", "Kế toán · không gian riêng") }
            if (state.financeOn) {
                tile("Tài chính & tiền thủ thuật", "Đối soát, phiếu thu, chính sách và chốt kỳ", "account_balance_wallet") { callbacks.onOpenFinance(0) }
            }
            tile("Thu ngân theo hồ sơ", state.profile.name, "receipt_long") { callbacks.onOpen(Routes.Cashier) }
            webOperationsItems(state.session, callbacks)
        }
        "doctor" -> {
            item { PemaHeading("Lịch & hồ sơ của tôi", state.session.staffName) }
            tile("Hồ sơ đang phụ trách", state.profile.name, "person") { callbacks.onOpen(Routes.Patient360) }
            tile("Lịch của tôi", state.patient.day.ifEmpty { "Chưa có lịch" }, "calendar_month") { callbacks.onOpen(Routes.AppointmentDetail) }
            if (state.financeOn) {
                tile("Doanh số của tôi", "Chỉ số cá nhân và tiền thủ thuật", "account_balance_wallet") { callbacks.onOpenFinance(0) }
            }
            item { PemaSection("Cập nhật cần bác sĩ xem") }
            state.reviewProfiles.forEach { profile ->
                tile(profile.name, "Review chăm sóc · hồ sơ phụ trách", "inbox") {
                    callbacks.onPatientSelected(state.catalog.indexOf(profile.id))
                    callbacks.onOpen(Routes.FollowUpReply)
                }
            }
            webOperationsItems(state.session, callbacks)
        }
        else -> {
            item {
                if (deps != null) {
                    CareQueueWidget(deps, onOpen = { callbacks.onOpen(Routes.CustomerCare) })
                } else {
                    PemaNotice("CareQueue – đang chuyển đổi")
                }
            }
            webOperationsItems(state.session, callbacks)
        }
    }
}

/**
 * Web-only clinic operations (canvas group I) the current role may open, listed after the
 * Flutter body. Order follows the web sidebar (`clinic.js` nav).
 */
private fun LazyListScope.webOperationsItems(session: Session, callbacks: WorkspaceCallbacks) {
    val entries = listOf(
        Routes.OpsDashboard to "space_dashboard",
        Routes.Reception to "how_to_reg",
        Routes.RoomSchedule to "meeting_room",
        Routes.AppointmentForm to "event_available",
        Routes.NewPatient to "person_add",
        Routes.FollowUpInbox to "inbox",
        Routes.PhotoStudio to "compare",
        Routes.RoomBlock to "block",
        Routes.ServiceEdit to "edit",
        Routes.CashierInvoices to "receipt_long",
        Routes.AskQuery to "manage_search",
    ).filter { session.allows(it.first) }
    if (entries.isEmpty()) return
    item { PemaSection("Vận hành phòng khám") }
    entries.forEach { (route, icon) ->
        val title = Routes.appBarTitleOf(route)
        tile(title, "Mở ${title.lowercase()}", icon) { callbacks.onOpen(route) }
    }
}

private fun LazyListScope.careItems(state: WorkspaceUiState, selectedTab: Int, callbacks: WorkspaceCallbacks) {
    val name = state.profile.name
    when (selectedTab) {
        1 -> {
            val journey = state.clinicPatient?.let { patientJourneyTimeline(it) }
            item { PemaHeading("Hành trình của bạn", "Mỗi bước chăm sóc đều được ghi nhận") }
            item {
                PemaHero(
                    "Phục hồi & chăm sóc da",
                    journey?.heroSubText ?: "${state.patient.sessions}/${state.profile.totalSessions} buổi đã hoàn tất",
                    "spa",
                )
            }
            listOf(
                "Kế hoạch điều trị" to Routes.TreatmentPlan,
                "Ảnh tiến triển" to Routes.ProgressPhotos,
                "Chăm sóc tại nhà" to Routes.HomeCare,
                "Đơn thuốc & tư vấn" to Routes.Prescriptions,
            ).forEach { (title, route) ->
                tile(title, "Xem chi tiết và hướng dẫn", "chevron_right") { callbacks.onOpen(route) }
            }
            // Canvas K3 (patient-mobile journey): recent updates timeline.
            if (journey != null && journey.updates.isNotEmpty()) {
                item { PemaSection(journey.sectionTitle) }
                journey.updates.forEach { update -> tile(update.dateLabel, update.title, update.icon, null) }
            }
        }
        2 -> {
            item { PemaHeading("Tin nhắn", "Đội ngũ Pema luôn đồng hành") }
            item { PemaNotice("Nếu có dấu hiệu bất thường nặng, hãy liên hệ trực tiếp. Tin nhắn không phải kênh cấp cứu.") }
            // Clinic messages sent from Patient 360 (canvas J9) as on patient-mobile web.
            state.clinicPatient?.messages?.filter { it.from == "clinic" }?.forEach { message ->
                tile("Đội ngũ Pema · ${message.date}", message.text, "forum", null)
            }
            state.patient.updates.forEach { update -> tile("Bạn", update, "chat_bubble_outline", null) }
            if (state.patient.response.isNotEmpty()) tile("Đội ngũ Pema", state.patient.response, "verified", null)
            item { PemaPrimary("Gửi cập nhật", onClick = { callbacks.onOpen(Routes.SendUpdate) }) }
        }
        3 -> {
            item { PemaHeading(name, "${state.profile.id} · Hồ sơ minh họa") }
            item { AccountPicker(state, callbacks) }
            listOf(
                "Đơn thuốc & tư vấn" to Routes.Prescriptions,
                "Hóa đơn" to Routes.Invoices,
                "Quyền riêng tư" to Routes.Privacy,
                "Hướng dẫn" to Routes.Guide,
                Routes.titleOf(Routes.PatientDocuments) to Routes.PatientDocuments,
            ).forEach { (title, route) ->
                tile(title, "Thông tin của bạn", "chevron_right") { callbacks.onOpen(route) }
            }
        }
        else -> {
            item { PemaHeading("Chào ${name.substringAfterLast(' ')},", "Hôm nay, dành chút thời gian cho làn da") }
            item { PatientNext(state, callbacks) }
            item {
                Column {
                    PemaHero(
                        "Chăm sóc nhẹ nhàng.\nĐồng hành mỗi ngày.",
                        "Liệu trình phục hồi · Buổi ${state.patient.sessions}/${state.profile.totalSessions}",
                        "spa",
                    )
                    Spacer(Modifier.height(16.dp))
                }
            }
            item {
                PemaActions(
                    listOf(
                        PemaAction("Chăm sóc", "favorite_border") { callbacks.onOpen(Routes.HomeCare) },
                        PemaAction("Gửi cập nhật", "add_a_photo") { callbacks.onOpen(Routes.SendUpdate) },
                        PemaAction("Đơn đã duyệt", "receipt_long") { callbacks.onOpen(Routes.Prescriptions) },
                    ),
                )
            }
            item { PemaSection("Lịch hẹn tiếp theo") }
            tile(
                if (state.patient.day.isEmpty()) "Chưa có lịch hẹn" else "${state.patient.appointment} · ${state.patient.day}",
                "BS. Tâm · Khám da liễu",
                "calendar_today",
            ) { callbacks.onOpen(Routes.PatientAppointments) }
            item { PemaSection("Việc cần làm") }
            tile(
                if (state.patient.acknowledged) "Đã đọc hướng dẫn" else "Đọc hướng dẫn sau điều trị",
                "Bác sĩ đã gửi hướng dẫn cho bạn",
                if (state.patient.acknowledged) "check_circle_outline" else "favorite_border",
            ) { callbacks.onOpen(Routes.HomeCare) }
        }
    }
}

@Composable
private fun PatientNext(state: WorkspaceUiState, callbacks: WorkspaceCallbacks) {
    val title = when (state.profile.careGroup) {
        "d1" -> "Hôm nay bạn cảm thấy thế nào?"
        "d3" -> "Cập nhật ảnh tiến triển"
        "d7" -> "Cùng bác sĩ xem lại tiến triển"
        "due" -> "Đến mốc tái khám"
        "overdue" -> "Sắp xếp lần tái khám tiếp theo"
        "no_show" -> "Chọn lại một lịch hẹn phù hợp"
        "abandoned" -> "Tiếp tục kế hoạch chăm sóc"
        "dormant90" -> "Pema sẵn sàng đồng hành"
        "dormant180" -> "Kết nối lại với Pema"
        "birthday" -> "Pema chúc bạn sinh nhật nhiều sức khỏe"
        else -> null
    }
    if (title != null) {
        PemaTile(
            title,
            "Xem lịch hoặc gửi nhu cầu để đội ngũ hỗ trợ",
            "favorite_border",
            { callbacks.onOpen(if (state.profile.careGroup == "due") Routes.MyAppointments else Routes.SendUpdate) },
        )
    }
}

@Composable
private fun AccountPicker(state: WorkspaceUiState, callbacks: WorkspaceCallbacks) {
    PemaSection("Tài khoản mẫu · 10 nhóm CSKH")
    val groupKeys = listOf("all") + state.catalog.profiles.filter { it.inCareQueue }.map { it.careGroup }
    PemaDropdownField(
        value = state.careGroup,
        options = groupKeys,
        onSelected = callbacks.onGroupSelected,
        display = { key ->
            if (key == "all") "Tất cả hồ sơ" else state.catalog.profiles.firstOrNull { it.careGroup == key }?.caseLabel.orEmpty()
        },
    )
    Spacer(Modifier.height(12.dp))
    val profileOptions = state.catalog.profiles.indices.filter { index ->
        state.careGroup == "all" || state.catalog.profiles[index].careGroup == state.careGroup
    }
    val value = if (state.session.selected in profileOptions) state.session.selected else profileOptions.first()
    PemaDropdownField(
        value = value,
        options = profileOptions,
        onSelected = callbacks.onPatientSelected,
        label = "Người bệnh đang xem",
        display = { index ->
            val profile = state.catalog.profiles[index]
            "${profile.id} · ${profile.name}"
        },
    )
}

@Composable
private fun FinanceSummaryTile(financeState: FinanceState, onTap: () -> Unit) {
    val data = financeState.data
    val subtitle = if (data == null) {
        "Doanh số · thực thu · tiền thủ thuật"
    } else {
        "Tháng ${financeState.month} · ${money(data.summary.revenue)}"
    }
    PemaTile("Tài chính phòng khám", subtitle, "account_balance_wallet", onTap)
}

private fun LazyListScope.patientSearchArea(search: PatientSearchState?, onOpen: () -> Unit) {
    if (search != null) {
        patientSearchItems(search, onOpen)
    } else {
        item { PemaNotice("PatientSearch ? ?ang chuy?n ??i") }
    }
}

/** Tabs that list sample profiles: owner "H? s?", staff "H? s? m?u". */
private fun showsPatientSearch(session: Session, tab: Int): Boolean =
    !session.careMode && tab == if (session.staffRole == "owner") 2 else 1

@Composable
private fun AccountSheetOverlay(onSelect: (WorkspaceAccount) -> Unit) {
    Box(Modifier.fillMaxSize().background(PemaColors.Black54)) {
        Column(
            Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .heightIn(max = 718.dp)
                .clip(RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp))
                .background(Color.White),
        ) {
            Box(Modifier.fillMaxWidth().height(48.dp), contentAlignment = Alignment.Center) {
                Box(Modifier.clip(RoundedCornerShape(2.dp)).background(PemaColors.OnSurfaceVariant.copy(alpha = 0.4f)).height(4.dp).fillMaxWidth(0.08f))
            }
            AccountSheetContent(onSelect = onSelect, modifier = Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()))
            Spacer(Modifier.height(34.dp))
        }
    }
}

@Composable
fun AccountSheetContent(
    onSelect: (WorkspaceAccount) -> Unit,
    modifier: Modifier = Modifier,
) {
    // No own scroll: PemaBottomSheet already scrolls, and nested verticalScroll crashes.
    Column(
        modifier
            .fillMaxWidth()
            .padding(20.dp),
    ) {
        Text("Duyệt không gian làm việc", style = PemaType.of(20f, FontWeight.W700, PemaColors.Ink, height = 1.3f))
        Text("Dữ liệu mẫu • chưa phải đăng nhập/phân quyền", style = PemaType.body)
        workspaceAccounts.forEach { account ->
            PemaListRow(
                title = "${account.name} · ${account.description}",
                leadingIcon = if (account.kind == "patient") "favorite_border" else "badge",
                onClick = { onSelect(account) },
                contentPadding = PaddingValues(start = 16.dp, end = 24.dp),
            )
        }
    }
}

@Composable
fun GuideScreen(route: String = Routes.titleOf(Routes.Guide)) {
    DetailScaffold(title = route) {
        PemaHeading("Một hành trình, nhiều điểm nối", "Hướng dẫn sử dụng Pema")
        listOf(
            "Tiếp nhận → lịch → Patient 360",
            "Dịch vụ → kế hoạch → buổi điều trị",
            "Đơn nháp → bác sĩ duyệt → người bệnh xem",
            "Cập nhật tại nhà → theo dõi → phản hồi",
            "Hóa đơn → thu tiền → đối soát",
        ).forEach { title ->
            PemaTile(title, "Mỗi bàn giao cần người phụ trách và bước tiếp theo.", "route", null)
        }
        PemaNotice("Duyệt Clinic/Care qua nút góc trên. Thao tác mẫu lưu trong bộ nhớ, tải lại sẽ bắt đầu phiên mới.")
    }
}

private fun roleLabel(session: Session): String = when {
    session.careMode -> "Care"
    session.staffRole == "owner" -> "Clinic"
    session.staffRole == "care" -> "CSKH"
    session.staffRole == "doctor" -> "Bác sĩ"
    else -> "Kế toán"
}

private fun tabsFor(session: Session): List<PemaNavItem> = when {
    session.careMode -> listOf(
        PemaNavItem("Trang chủ", "home", "home"),
        PemaNavItem("Hành trình", "route", "alt_route"),
        PemaNavItem("Tin nhắn", "chat_bubble_outline", "chat_bubble"),
        PemaNavItem("Hồ sơ", "person", "person"),
    )
    session.staffRole != "owner" -> listOf(
        PemaNavItem("Công việc", "work", "work"),
        PemaNavItem("Hồ sơ mẫu", "people_outline", "people"),
    )
    else -> listOf(
        PemaNavItem("Hôm nay", "space_dashboard", "space_dashboard"),
        PemaNavItem("Lịch hẹn", "calendar_month", "calendar_month"),
        PemaNavItem("Hồ sơ", "people_outline", "people"),
        PemaNavItem("Theo dõi", "inbox", "inbox"),
        PemaNavItem("Thêm", "grid_view", "grid_view"),
    )
}
