package com.pema.clinic.feature.operations

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import androidx.savedstate.read
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.Gap
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.core.ui.widgets.PemaCardFilledButton
import com.pema.clinic.core.ui.widgets.PemaCardLine
import com.pema.clinic.core.ui.widgets.PemaCardTextButtons
import com.pema.clinic.core.ui.widgets.PemaCardTitle
import com.pema.clinic.core.ui.widgets.PemaCareRow
import com.pema.clinic.core.ui.widgets.PemaChipWrap
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.PemaExtendedFab
import com.pema.clinic.core.ui.widgets.PemaFilterChip
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaInfoCard
import com.pema.clinic.core.ui.widgets.PemaMetrics
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaText
import com.pema.clinic.core.ui.widgets.PemaTextButton
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.core.ui.widgets.WeekStrip
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.clinic.Appointment
import com.pema.clinic.shared.clinic.AppointmentInput
import com.pema.clinic.shared.clinic.ClinicError
import com.pema.clinic.shared.clinic.ClinicState
import com.pema.clinic.shared.clinic.ClinicStore
import com.pema.clinic.shared.clinic.CrmInput
import com.pema.clinic.shared.clinic.DAY
import com.pema.clinic.shared.clinic.RoomBlock
import com.pema.clinic.shared.clinic.ServiceUpdate
import com.pema.clinic.shared.clinic.addDays
import com.pema.clinic.shared.clinic.block
import com.pema.clinic.shared.clinic.clearPreparedCrmBooking
import com.pema.clinic.shared.clinic.crmQueue
import com.pema.clinic.shared.clinic.initials
import com.pema.clinic.shared.clinic.minutes
import com.pema.clinic.shared.clinic.money
import com.pema.clinic.shared.clinic.patient
import com.pema.clinic.shared.clinic.preparedCrmBookingInput
import com.pema.clinic.shared.clinic.reception
import com.pema.clinic.shared.clinic.saveAppointment
import com.pema.clinic.shared.clinic.staffContext
import com.pema.clinic.shared.clinic.time
import com.pema.clinic.shared.clinic.updateService
import com.pema.clinic.shared.clinic.validate
import com.pema.clinic.shared.clinic.viDate

/** Vietnamese weekday short label (T2…T7, CN) for an ISO date. */
internal fun weekdayLabel(day: String): String =
    when (kotlinx.datetime.LocalDate.parse(day).dayOfWeek) {
        kotlinx.datetime.DayOfWeek.MONDAY -> "T2"
        kotlinx.datetime.DayOfWeek.TUESDAY -> "T3"
        kotlinx.datetime.DayOfWeek.WEDNESDAY -> "T4"
        kotlinx.datetime.DayOfWeek.THURSDAY -> "T5"
        kotlinx.datetime.DayOfWeek.FRIDAY -> "T6"
        kotlinx.datetime.DayOfWeek.SATURDAY -> "T7"
        else -> "CN"
    }

fun NavGraphBuilder.operationsGraph(deps: FeatureDeps) {
    composable(Routes.OpsDashboard) { OperationsDashboardRoute(deps) }
    composable(Routes.Reception) { ReceptionRoute(deps) }
    composable(Routes.RoomSchedule) { RoomScheduleRoute(deps) }
    composable(
        route = AppointmentFormPattern,
        arguments = listOf(
            navArgument("id") { type = NavType.StringType; defaultValue = "" },
            navArgument("patient") { type = NavType.StringType; defaultValue = "" },
            navArgument("crmTask") { type = NavType.StringType; defaultValue = "" },
        ),
    ) { entry ->
        AppointmentFormRoute(
            deps,
            entry.arguments?.read { getStringOrNull("id") }.orEmpty(),
            entry.arguments?.read { getStringOrNull("patient") }.orEmpty(),
            entry.arguments?.read { getStringOrNull("crmTask") }.orEmpty(),
        )
    }
    composable(Routes.RoomBlock) { RoomBlockRoute(deps) }
    composable(
        route = ServiceEditPattern,
        arguments = listOf(navArgument("id") { type = NavType.StringType; defaultValue = "S2" }),
    ) { entry ->
        ServiceEditRoute(deps, entry.arguments?.read { getStringOrNull("id") }.orEmpty().ifBlank { "S2" })
    }
}

internal const val AppointmentFormPattern = "appointment-form?id={id}&patient={patient}&crmTask={crmTask}"
internal const val ServiceEditPattern = "service-edit?id={id}"

@Composable
private fun OperationsDashboardRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    OperationsDashboardScreen(
        state = dashboardState(clinic, session.staffContext().name),
        onOpenCashier = { deps.navigator.go(Routes.CashierInvoices) },
        onCare = { patientId ->
            val index = deps.catalogRepository.catalog().profiles.indexOfFirst { it.id == patientId }
            if (index >= 0) deps.sessionStore.select(index)
            deps.navigator.go(Routes.CareRecord)
        },
    )
}

@Composable
private fun ReceptionRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    var filter by rememberSaveable { mutableStateOf(ReceptionFilter.All) }
    val messenger = rememberPemaMessenger()
    ReceptionScreen(
        state = receptionState(clinic, filter, session.staffContext().let { if (it.role == "doctor") it.doctorId else null }),
        onFilter = { filter = it },
        onNewAppointment = { deps.navigator.go(Routes.AppointmentForm) },
        onReception = { id, status ->
            runCatching {
                deps.clinicStore.reception(id, status)
            }.onSuccess {
                messenger.show("Đã cập nhật hàng đợi")
            }.onFailure {
                messenger.show(it.message ?: "Không thể cập nhật lịch.")
            }
        },
    )
}

@Composable
private fun RoomScheduleRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    var date by rememberSaveable { mutableStateOf(DAY) }
    var room by rememberSaveable { mutableStateOf("all") }
    RoomScheduleScreen(
        state = roomScheduleState(clinic, date, room),
        onDate = { date = it },
        onRoom = { room = it },
        onAppointment = { id -> deps.navigator.go(Routes.withArgs(Routes.AppointmentForm, "id" to id)) },
    )
}

@Composable
private fun AppointmentFormRoute(deps: FeatureDeps, appointmentId: String, patientIdArg: String, crmTaskId: String) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val staff = session.staffContext()
    val existing = clinic.operations.appointments.find { it.id == appointmentId }
    val crmTaskPatient = clinic.crmTasks.firstOrNull { it.id == crmTaskId }?.patientId
    val defaultPatient = patientIdArg.ifBlank { crmTaskPatient ?: existing?.patient ?: deps.sessionStore.selectedPatientId() }
    val firstService = existing?.service ?: clinic.operations.services.firstOrNull()?.id.orEmpty()
    val service = clinic.operations.services.find { it.id == firstService } ?: clinic.operations.services.first()
    var patient by rememberSaveable(appointmentId, patientIdArg) { mutableStateOf(defaultPatient) }
    var serviceId by rememberSaveable(appointmentId) { mutableStateOf(service.id) }
    var doctor by rememberSaveable(appointmentId, staff.doctorId) { mutableStateOf(existing?.doctor ?: staff.doctorId ?: clinic.operations.doctors.first().id) }
    var room by rememberSaveable(appointmentId) { mutableStateOf(existing?.room ?: service.rooms.first()) }
    var date by rememberSaveable(appointmentId) { mutableStateOf(existing?.date ?: addDays(DAY, 2)) }
    var slot by rememberSaveable(appointmentId) { mutableStateOf(existing?.time ?: "10:30") }
    val messenger = rememberPemaMessenger()
    val uiState = appointmentFormState(clinic, appointmentId.ifBlank { null }, patient, serviceId, doctor, room, date, slot, staff.role == "doctor")
    AppointmentFormScreen(
        state = uiState,
        onPatient = { patient = it },
        onService = {
            serviceId = it
            val nextService = clinic.operations.services.first { s -> s.id == it }
            if (room !in nextService.rooms) room = nextService.rooms.first()
        },
        onDoctor = { doctor = it },
        onRoom = { room = it },
        onSlot = { slot = it },
        onFindSlot = {
            val found = findFirstValidSlot(clinic, uiState)
            if (found != null) {
                slot = found
                messenger.show("Đã chọn giờ trống. Bấm xác nhận để lưu.")
            } else {
                messenger.show("Không có giờ trống cho lựa chọn này. Hãy đổi ngày, bác sĩ hoặc phòng.")
            }
        },
        onSave = {
            runCatching {
                deps.clinicStore.saveAppointment(
                    AppointmentInput(
                        id = appointmentId.ifBlank { null },
                        patient = patient,
                        service = serviceId,
                        doctor = doctor,
                        room = room,
                        date = date,
                        time = slot,
                        crmTaskId = crmTaskId.ifBlank { null },
                        crmInput = crmBookingInput(deps.clinicStore, clinic, crmTaskId),
                    ),
                    staff,
                )
            }.onSuccess {
                if (crmTaskId.isNotBlank()) deps.clinicStore.clearPreparedCrmBooking(crmTaskId)
                messenger.show("Đã lưu lịch và cập nhật Patient 360")
                deps.navigator.back()
            }.onFailure {
                messenger.show(it.message ?: "Không thể lưu lịch.")
            }
        },
    )
}

@Composable
private fun RoomBlockRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    var room by rememberSaveable { mutableStateOf("R2") }
    var date by rememberSaveable { mutableStateOf(addDays(DAY, 1)) }
    var start by rememberSaveable { mutableStateOf("14:00") }
    var end by rememberSaveable { mutableStateOf("15:00") }
    var reason by rememberSaveable { mutableStateOf("Bảo trì thiết bị laser") }
    val messenger = rememberPemaMessenger()
    RoomBlockScreen(
        state = roomBlockState(clinic, room, date, start, end, reason),
        onRoom = { room = it },
        onStart = { start = it },
        onEnd = { end = it },
        onReason = { reason = it },
        onSave = {
            runCatching {
                deps.clinicStore.block(RoomBlock("", room, date = date, start = start, end = end, reason = reason), session.staffContext())
            }.onSuccess {
                messenger.show("Đã khóa phòng")
            }.onFailure {
                messenger.show(it.message ?: "Không thể khóa phòng.")
            }
        },
    )
}

@Composable
private fun ServiceEditRoute(deps: FeatureDeps, id: String) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val service = clinic.operations.services.find { it.id == id } ?: clinic.operations.services.first { it.id == "S2" }
    var name by rememberSaveable(id) { mutableStateOf(service.name) }
    var duration by rememberSaveable(id) { mutableStateOf(service.duration.toString()) }
    var buffer by rememberSaveable(id) { mutableStateOf(service.buffer.toString()) }
    var price by rememberSaveable(id) { mutableStateOf(service.price.toString()) }
    var active by rememberSaveable(id) { mutableStateOf(if (service.active) "yes" else "no") }
    val messenger = rememberPemaMessenger()
    ServiceEditScreen(
        state = serviceEditState(clinic, id, name, duration, buffer, price, active == "yes"),
        onName = { name = it },
        onDuration = { duration = it },
        onBuffer = { buffer = it },
        onPrice = { price = it },
        onActive = { active = if (it) "yes" else "no" },
        onSave = {
            runCatching {
                val current = clinic.operations.services.find { it.id == id } ?: service
                deps.clinicStore.updateService(
                    current.id,
                    ServiceUpdate(
                        name = name.trim(),
                        duration = duration.toIntOrNull() ?: -1,
                        buffer = buffer.toIntOrNull() ?: -1,
                        price = price.toIntOrNull() ?: -1,
                        active = active == "yes",
                        rooms = current.rooms,
                    ),
                    session.staffContext(),
                )
            }.onSuccess {
                messenger.show("Đã cập nhật dịch vụ cho lịch mới")
            }.onFailure {
                messenger.show(it.message ?: "Không thể lưu dịch vụ.")
            }
        },
    )
}

@Composable
internal fun OperationsDashboardScreen(
    state: DashboardUiState,
    onOpenCashier: () -> Unit = {},
    onCare: (String) -> Unit = {},
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.OpsDashboard), onBack = onBack) {
        PemaHeading("Chào buổi sáng, ${state.staffName}", "Vận hành hôm nay và CSKH · ${state.displayDate}")
        PemaMetrics(
            state.todayAppointments to "Lịch hôm nay",
            state.arrivedAndWaiting to "Đến / chờ",
            state.missed to "Vắng hẹn",
        )
        Gap(16)
        PemaTile(
            title = "Phát sinh hôm nay",
            sub = "${state.invoiceTotal} · hóa đơn, không phải thực thu",
            icon = "receipt_long",
            onClick = onOpenCashier,
        )
        PemaSection("CSKH")
        PemaMetrics(
            state.carePatients to "Cần CSKH",
            state.overduePatients to "Quá hạn",
            state.atRiskPatients to "Nguy cơ mất",
        )
        PemaSection("Ưu tiên chăm sóc")
        state.careRows.forEach { row ->
            PemaCareRow(
                initials = row.initials,
                name = row.name,
                group = row.group,
                meta = row.meta,
                onClick = { onCare(row.patientId) },
            )
        }
        PemaNotice("Khách đặt lịch chưa được tính là đã quay lại. Chỉ ghi nhận quay lại khi check-in sau CSKH.")
    }
}

@Composable
internal fun ReceptionScreen(
    state: ReceptionUiState,
    onFilter: (String) -> Unit = {},
    onNewAppointment: () -> Unit = {},
    onReception: (String, String) -> Unit = { _, _ -> },
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(
        title = Routes.appBarTitleOf(Routes.Reception),
        onBack = onBack,
        floatingActionButton = { PemaExtendedFab("Đặt lịch mới", onClick = onNewAppointment) },
    ) {
        PemaHeading("Hôm nay tại Pema", "Tiếp đón theo từng lịch hẹn · ${state.displayDate}")
        PemaMetrics(
            state.total to "Tổng lịch",
            state.waiting to "Đang chờ",
            state.completed to "Hoàn tất",
        )
        Gap(16)
        PemaChipWrap {
            ReceptionFilter.options.forEach { (id, label) ->
                PemaFilterChip(label, selected = state.filter == id, onClick = { onFilter(id) })
            }
        }
        Gap(16)
        state.rows.forEach { row ->
            PemaInfoCard {
                PemaCardTitle("${row.time} · ${row.patientName}")
                PemaText("${row.patientId} · ${row.serviceName} · ${row.doctorName}", size = 12f, color = PemaColors.Muted)
                Gap(12)
                PemaCardLine("Trạng thái", row.statusLabel)
                PemaCardLine("Giá dự kiến", row.price)
                when (row.action) {
                    ReceptionAction.Arrive -> {
                        Gap(8)
                        PemaCardTextButtons(
                            "Check-in" to { onReception(row.id, "arrived") },
                            "Vắng" to { onReception(row.id, "missed") },
                        )
                    }
                    ReceptionAction.Start -> {
                        Gap(8)
                        PemaCardFilledButton("Mời vào phòng", onClick = { onReception(row.id, "in_progress") })
                    }
                    ReceptionAction.None -> Unit
                }
            }
        }
    }
}

@Composable
internal fun RoomScheduleScreen(
    state: RoomScheduleUiState,
    onDate: (String) -> Unit = {},
    onRoom: (String) -> Unit = {},
    onAppointment: (String) -> Unit = {},
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.RoomSchedule), onBack = onBack) {
        // Web schedule covers the 7 seeded days from DAY; tap a day to see its rooms.
        val days = remember { (0..6).map { addDays(DAY, it) } }
        WeekStrip(
            days = days.map { weekdayLabel(it) to it.takeLast(2).trimStart('0') },
            selected = days.indexOf(state.date).coerceAtLeast(0),
            onSelect = { onDate(days[it]) },
        )
        PemaDropdownField(
            value = state.selectedRoom,
            options = state.roomOptions.map { it.id },
            onSelected = onRoom,
            label = "Phòng",
            display = { id -> state.roomOptions.first { it.id == id }.name },
        )
        Gap(4)
        state.sections.forEachIndexed { index, section ->
            PemaSection("${section.roomName} · ${section.count} lịch")
            section.rows.forEach { row ->
                PemaTile(
                    title = row.timeRange,
                    sub = "${row.patientName} · ${row.serviceName} · ${row.doctorName}",
                    icon = "schedule",
                    onClick = { onAppointment(row.id) },
                )
            }
            if (index == 1 || index == state.sections.lastIndex) {
                PemaNotice(state.notice)
            }
        }
    }
}

@Composable
internal fun AppointmentFormScreen(
    state: AppointmentFormUiState,
    onPatient: (String) -> Unit = {},
    onService: (String) -> Unit = {},
    onDoctor: (String) -> Unit = {},
    onRoom: (String) -> Unit = {},
    onSlot: (String) -> Unit = {},
    onFindSlot: () -> Unit = {},
    onSave: () -> Unit = {},
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.AppointmentForm), onBack = onBack) {
        PemaDropdownField(
            value = state.patient,
            options = state.patientOptions.map { it.id },
            onSelected = onPatient,
            label = "Bệnh nhân",
            display = { id -> state.patientOptions.first { it.id == id }.label },
        )
        Gap(14)
        PemaDropdownField(
            value = state.service,
            options = state.serviceOptions.map { it.id },
            onSelected = onService,
            label = "Dịch vụ",
            display = { id -> state.serviceOptions.first { it.id == id }.label },
        )
        Gap(14)
        PemaDropdownField(
            value = state.doctor,
            options = state.doctorOptions.map { it.id },
            onSelected = onDoctor,
            label = "Bác sĩ",
            display = { id -> state.doctorOptions.first { it.id == id }.label },
            enabled = !state.doctorFixed,
        )
        Gap(14)
        PemaDropdownField(
            value = state.room,
            options = state.roomOptions.map { it.id },
            onSelected = onRoom,
            label = "Phòng",
            display = { id -> state.roomOptions.first { it.id == id }.label },
        )
        Gap(6)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
            PemaTextButton("Ngày ${viDate(state.date)}", onClick = {}, icon = "calendar_month", iconFilled = true)
        }
        PemaChipWrap {
            state.slots.forEach { slot ->
                PemaFilterChip(slot.time, selected = slot.selected, enabled = slot.valid, onClick = { onSlot(slot.time) })
            }
        }
        PemaNotice(state.preview)
        PemaPrimary("Xác nhận đặt lịch", onClick = onSave)
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            PemaTextButton("Tìm giờ trống", onClick = onFindSlot, icon = "search")
        }
    }
}

@Composable
internal fun RoomBlockScreen(
    state: RoomBlockUiState,
    onRoom: (String) -> Unit = {},
    onStart: (String) -> Unit = {},
    onEnd: (String) -> Unit = {},
    onReason: (String) -> Unit = {},
    onSave: () -> Unit = {},
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.RoomBlock), onBack = onBack) {
        PemaDropdownField(
            value = state.room,
            options = state.rooms.map { it.id },
            onSelected = onRoom,
            label = "Phòng",
            display = { id -> state.rooms.first { it.id == id }.label },
        )
        Gap(6)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
            PemaTextButton("Ngày ${viDate(state.date)}", onClick = {}, icon = "calendar_month", iconFilled = true)
        }
        PemaTextField(state.start, onStart, label = "Từ")
        Gap(14)
        PemaTextField(state.end, onEnd, label = "Đến")
        Gap(14)
        PemaTextField(state.reason, onReason, label = "Lý do")
        Gap(8)
        PemaPrimary("Lưu khoảng khóa", onClick = onSave)
        PemaSection("Khoảng khóa hiện có")
        state.blocks.forEach { block ->
            PemaTile(
                title = "${block.roomName} · ${viDate(block.date)}",
                sub = "${block.start}–${block.end} · ${block.reason}",
                icon = "block",
                onClick = null,
            )
        }
    }
}

@Composable
internal fun ServiceEditScreen(
    state: ServiceEditUiState,
    onName: (String) -> Unit = {},
    onDuration: (String) -> Unit = {},
    onBuffer: (String) -> Unit = {},
    onPrice: (String) -> Unit = {},
    onActive: (Boolean) -> Unit = {},
    onSave: () -> Unit = {},
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.ServiceEdit), onBack = onBack) {
        PemaTextField(state.name, onName, label = "Tên dịch vụ")
        Gap(14)
        PemaTextField(state.duration, onDuration, label = "Điều trị (phút)", keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        Gap(14)
        PemaTextField(state.buffer, onBuffer, label = "Chuẩn bị (phút)", keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        Gap(14)
        PemaTextField(state.price, onPrice, label = "Giá (VND)", keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        Gap(14)
        PemaDropdownField(
            value = if (state.active) "yes" else "no",
            options = listOf("yes", "no"),
            onSelected = { onActive(it == "yes") },
            label = "Trạng thái",
            display = { if (it == "yes") "Đang dùng" else "Tạm ngưng" },
        )
        Gap(16)
        PemaNotice("Lịch đã đặt giữ giá và thời lượng tại lúc đặt.")
        PemaPrimary("Lưu dịch vụ", onClick = onSave)
    }
}

@Immutable
internal data class DashboardUiState(
    val staffName: String,
    val displayDate: String,
    val todayAppointments: String,
    val arrivedAndWaiting: String,
    val missed: String,
    val invoiceTotal: String,
    val carePatients: String,
    val overduePatients: String,
    val atRiskPatients: String,
    val careRows: List<CareRowUi>,
)

@Immutable
internal data class CareRowUi(val patientId: String, val initials: String, val name: String, val group: String, val meta: String)

@Immutable
internal data class ReceptionUiState(
    val displayDate: String,
    val total: String,
    val waiting: String,
    val completed: String,
    val filter: String,
    val rows: List<ReceptionRowUi>,
)

@Immutable
internal data class ReceptionRowUi(
    val id: String,
    val time: String,
    val patientId: String,
    val patientName: String,
    val serviceName: String,
    val doctorName: String,
    val statusLabel: String,
    val price: String,
    val action: ReceptionAction,
)

internal enum class ReceptionAction { Arrive, Start, None }

@Immutable
internal data class RoomScheduleUiState(
    val date: String,
    val selectedRoom: String,
    val roomOptions: List<OptionUi>,
    val sections: List<RoomSectionUi>,
    val notice: String,
)

@Immutable
internal data class RoomSectionUi(val roomName: String, val count: Int, val rows: List<ScheduleRowUi>)

@Immutable
internal data class ScheduleRowUi(
    val id: String,
    val timeRange: String,
    val patientName: String,
    val serviceName: String,
    val doctorName: String,
)

@Immutable
internal data class AppointmentFormUiState(
    val id: String?,
    val patient: String,
    val service: String,
    val doctor: String,
    val room: String,
    val date: String,
    val slots: List<SlotUi>,
    val preview: String,
    val patientOptions: List<OptionUi>,
    val serviceOptions: List<OptionUi>,
    val doctorOptions: List<OptionUi>,
    val roomOptions: List<OptionUi>,
    val doctorFixed: Boolean,
)

@Immutable
internal data class SlotUi(val time: String, val selected: Boolean, val valid: Boolean)

@Immutable
internal data class OptionUi(val id: String, val label: String) {
    val name: String get() = label
}

@Immutable
internal data class RoomBlockUiState(
    val room: String,
    val date: String,
    val start: String,
    val end: String,
    val reason: String,
    val rooms: List<OptionUi>,
    val blocks: List<BlockRowUi>,
)

@Immutable
internal data class BlockRowUi(val roomName: String, val date: String, val start: String, val end: String, val reason: String)

@Immutable
internal data class ServiceEditUiState(
    val id: String,
    val name: String,
    val duration: String,
    val buffer: String,
    val price: String,
    val active: Boolean,
)

internal object ReceptionFilter {
    const val All = "all"
    const val NotArrived = "not_arrived"
    const val Waiting = "waiting"
    const val Missed = "missed"
    val options = listOf(All to "Tất cả", NotArrived to "Chưa đến", Waiting to "Đang chờ", Missed to "Vắng hẹn")
}

internal fun dashboardState(state: ClinicState, staffName: String = "BS. Tâm"): DashboardUiState {
    val appointments = state.operations.appointments.filter { it.date == DAY }
    val crmQueue = state.crmQueue()
    val rows = crmQueue.distinctBy { it.patientId }.take(3).map { task ->
        val patient = state.patient(task.patientId)
        CareRowUi(
            patientId = patient.id,
            initials = initials(patient.name),
            name = patient.name,
            group = careGroupLabel(task.type),
            meta = "${patient.id} · ${patient.doctor}",
        )
    }
    val revenue = state.patients.flatMap { it.invoices }.filter { it.date == DAY }.sumOf { it.amount }
    return DashboardUiState(
        staffName = staffName,
        displayDate = viDate(DAY),
        todayAppointments = appointments.size.toString(),
        arrivedAndWaiting = "${appointments.count { it.status in setOf("arrived", "in_progress", "completed") }}/${appointments.count { it.status == "arrived" }}",
        missed = appointments.count { it.status == "missed" }.toString(),
        invoiceTotal = money(revenue),
        carePatients = crmQueue.map { it.patientId }.toSet().size.toString(),
        overduePatients = state.patients.count { it.crm.overdueDays > 0 }.toString(),
        atRiskPatients = state.patients.count { it.crm.riskLevel == "high" }.toString(),
        careRows = rows,
    )
}

internal fun receptionState(state: ClinicState, filter: String = ReceptionFilter.All, doctorId: String? = null): ReceptionUiState {
    val all = state.operations.appointments
        .filter { it.date == DAY && (doctorId == null || it.doctor == doctorId) }
        .sortedBy { it.time }
    val rows = applyReceptionFilter(all, filter).map { appointment ->
        val patient = state.patient(appointment.patient)
        val service = state.operations.services.first { it.id == appointment.service }
        val doctor = state.operations.doctors.first { it.id == appointment.doctor }
        ReceptionRowUi(
            id = appointment.id,
            time = appointment.time,
            patientId = patient.id,
            patientName = patient.name,
            serviceName = service.name,
            doctorName = doctor.name,
            statusLabel = receptionStatusLabel(appointment.status),
            price = money(appointment.price),
            action = when (appointment.status) {
                "booked", "confirmed" -> ReceptionAction.Arrive
                "arrived" -> ReceptionAction.Start
                else -> ReceptionAction.None
            },
        )
    }
    return ReceptionUiState(
        displayDate = viDate(DAY),
        total = all.size.toString(),
        waiting = all.count { it.status == "arrived" }.toString(),
        completed = all.count { it.status == "completed" }.toString(),
        filter = filter,
        rows = rows,
    )
}

internal fun applyReceptionFilter(rows: List<Appointment>, filter: String): List<Appointment> = rows.filter {
    when (filter) {
        ReceptionFilter.NotArrived -> it.status in setOf("booked", "confirmed")
        ReceptionFilter.Waiting -> it.status == "arrived"
        ReceptionFilter.Missed -> it.status == "missed"
        else -> true
    }
}

internal fun roomScheduleState(state: ClinicState, date: String = DAY, selectedRoom: String = "all"): RoomScheduleUiState {
    val rooms = state.operations.rooms
    val appointments = state.operations.appointments
        .filter { it.date == date && it.isUiActive() && (selectedRoom == "all" || it.room == selectedRoom) }
        .sortedBy { it.time }
    val roomOrder = listOf("R0", "R2", "R1", "R3")
    val sections = rooms.sortedBy { roomOrder.indexOf(it.id).let { index -> if (index < 0) Int.MAX_VALUE else index } }
        .filter { selectedRoom == "all" || it.id == selectedRoom }
        .mapNotNull { room ->
            val rows = appointments.filter { it.room == room.id }
            if (rows.isEmpty()) null else RoomSectionUi(
                roomName = room.name,
                count = rows.size,
                rows = rows.take(if (room.id == "R2") 1 else 2).map { a ->
                    val patient = state.patient(a.patient)
                    val service = state.operations.services.first { it.id == a.service }
                    val doctor = state.operations.doctors.first { it.id == a.doctor }
                    val end = time(minutes(a.time)!! + a.duration)
                    ScheduleRowUi(
                        id = a.id,
                        timeRange = "${a.time}–$end${if (a.buffer > 0) " · +${a.buffer}′ đệm" else ""}",
                        patientName = patient.name,
                        serviceName = service.name,
                        doctorName = doctor.name,
                    )
                },
            )
        }
    val maxBuffer = state.operations.services.maxOfOrNull { it.buffer } ?: 0
    val waiting = state.operations.waitlist.count { it.status == "waiting" }
    return RoomScheduleUiState(
        date = date,
        selectedRoom = selectedRoom,
        roomOptions = listOf(OptionUi("all", "Tất cả phòng")) + rooms.map { OptionUi(it.id, it.name) },
        sections = sections,
        notice = "${maxBuffer}′ chuẩn bị phòng sau thủ thuật · $waiting lịch chờ xếp · khoảng khóa phòng được kiểm tra khi dời lịch.",
    )
}

internal fun appointmentFormState(
    state: ClinicState,
    id: String?,
    patient: String,
    serviceId: String,
    doctorId: String,
    roomId: String,
    date: String,
    selectedSlot: String,
    doctorFixed: Boolean = false,
): AppointmentFormUiState {
    val service = state.operations.services.find { it.id == serviceId } ?: state.operations.services.first()
    val old = id?.let { state.operations.appointments.find { a -> a.id == it } }
    val same = old?.service == service.id
    val duration = if (same) old!!.duration else service.duration
    val buffer = if (same) old!!.buffer else service.buffer
    val price = if (same) old!!.price else service.price
    val room = if (roomId in service.rooms) roomId else service.rooms.first()
    val slots = BookingSlots.map { slot ->
        SlotUi(
            time = slot,
            selected = slot == selectedSlot,
            valid = appointmentValid(state, id, patient, service.id, doctorId, room, date, slot, duration, buffer, price),
        )
    }
    return AppointmentFormUiState(
        id = id,
        patient = patient,
        service = service.id,
        doctor = doctorId,
        room = room,
        date = date,
        slots = slots,
        preview = "$duration phút điều trị + $buffer phút chuẩn bị · ${money(price)}${if (same) " · theo lịch đã đặt" else ""}",
        patientOptions = state.patients.map { OptionUi(it.id, "${it.id} · ${it.name}") },
        serviceOptions = state.operations.services.map { OptionUi(it.id, it.name) },
        doctorOptions = state.operations.doctors.map { OptionUi(it.id, it.name) },
        roomOptions = state.operations.rooms.filter { it.id in service.rooms }.map { OptionUi(it.id, it.name) },
        doctorFixed = doctorFixed,
    )
}

internal fun findFirstValidSlot(state: ClinicState, form: AppointmentFormUiState): String? {
    val service = state.operations.services.first { it.id == form.service }
    val old = form.id?.let { state.operations.appointments.find { a -> a.id == it } }
    val same = old?.service == service.id
    val duration = if (same) old!!.duration else service.duration
    val buffer = if (same) old!!.buffer else service.buffer
    val price = if (same) old!!.price else service.price
    for (minute in 480..1065 step 15) {
        val slot = time(minute)
        if (appointmentValid(state, form.id, form.patient, form.service, form.doctor, form.room, form.date, slot, duration, buffer, price)) return slot
    }
    return null
}

internal fun crmBookingInput(store: ClinicStore, state: ClinicState, crmTaskId: String): CrmInput? {
    if (crmTaskId.isBlank()) return null
    store.preparedCrmBookingInput(crmTaskId)?.let { return it }
    val task = state.crmTasks.firstOrNull { it.id == crmTaskId } ?: return null
    return CrmInput(
        channel = "Gọi điện",
        outcome = "booked",
        owner = task.owner,
        note = "Khách đồng ý đặt lịch theo tư vấn CSKH.",
        nextActionType = "book",
        priority = task.priority,
    )
}

internal fun roomBlockState(state: ClinicState, room: String, date: String, start: String, end: String, reason: String): RoomBlockUiState =
    RoomBlockUiState(
        room = room,
        date = date,
        start = start,
        end = end,
        reason = reason,
        rooms = state.operations.rooms.map { OptionUi(it.id, it.name) },
        blocks = state.operations.blocks.map { block ->
            BlockRowUi(
                roomName = state.operations.rooms.firstOrNull { it.id == block.room }?.name ?: block.room,
                date = block.date,
                start = block.start,
                end = block.end,
                reason = block.reason,
            )
        },
    )

internal fun serviceEditState(state: ClinicState, id: String, name: String, duration: String, buffer: String, price: String, active: Boolean): ServiceEditUiState {
    val service = state.operations.services.find { it.id == id } ?: state.operations.services.first { it.id == "S2" }
    return ServiceEditUiState(service.id, name, duration, buffer, price, active)
}

private val BookingSlots = listOf("09:00", "10:30", "11:00", "14:00")

private fun appointmentValid(
    state: ClinicState,
    id: String?,
    patient: String,
    service: String,
    doctor: String,
    room: String,
    date: String,
    slot: String,
    duration: Int,
    buffer: Int,
    price: Int,
): Boolean = try {
    state.validate(
        Appointment(
            id = id ?: "",
            patient = patient,
            doctor = doctor,
            room = room,
            service = service,
            date = date,
            time = slot,
            duration = duration,
            buffer = buffer,
            price = price,
            status = "booked",
        ),
    )
} catch (_: ClinicError) {
    false
}

private fun Appointment.isUiActive(): Boolean = status !in setOf("cancelled", "missed")

private fun receptionStatusLabel(status: String): String = when (status) {
    "booked" -> "Chưa đến"
    "confirmed" -> "Đã xác nhận"
    "arrived" -> "Đang chờ"
    "in_progress" -> "Đang khám/điều trị"
    "completed" -> "Hoàn tất"
    "cancelled" -> "Đã hủy"
    "missed" -> "Vắng hẹn"
    else -> "Đặt hẹn"
}

private fun careGroupLabel(type: String): String = when (type) {
    "d1" -> "Sau thủ thuật · D+1"
    "d3" -> "Ảnh tiến triển · D+3"
    "d7" -> "Bác sĩ review · D+7"
    "due" -> "Đến hạn tái khám"
    "overdue" -> "Quá hạn tái khám"
    "no_show" -> "Vắng hẹn"
    "abandoned" -> "Tiếp tục liệu trình"
    "dormant90" -> "Kết nối lại · 90 ngày"
    "dormant180" -> "Kết nối lại · 180 ngày"
    "birthday" -> "Sinh nhật trong tuần"
    else -> type
}
