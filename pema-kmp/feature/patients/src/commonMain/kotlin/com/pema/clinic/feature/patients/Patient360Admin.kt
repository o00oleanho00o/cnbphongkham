package com.pema.clinic.feature.patients

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.PemaCardLine
import com.pema.clinic.core.ui.widgets.PemaCardTitle
import com.pema.clinic.core.ui.widgets.PemaCheckRow
import com.pema.clinic.core.ui.widgets.PemaDialog
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.PemaEmpty
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaInfoCard
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaOutlinedButton
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaText
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.clinic.ClinicState
import com.pema.clinic.shared.clinic.DAY
import com.pema.clinic.shared.clinic.careFinanceSummary
import com.pema.clinic.shared.clinic.crmOutcomes
import com.pema.clinic.shared.clinic.crmQueue
import com.pema.clinic.shared.clinic.crmSources
import com.pema.clinic.shared.clinic.money
import com.pema.clinic.shared.clinic.saveHomeCareInstructions
import com.pema.clinic.shared.clinic.savePatientFacts
import com.pema.clinic.shared.clinic.sendPatientMessage
import com.pema.clinic.shared.clinic.setExpectedVisit
import com.pema.clinic.shared.clinic.staffContext
import com.pema.clinic.shared.clinic.viDate

fun NavGraphBuilder.patient360AdminGraph(deps: FeatureDeps) {
    composable(Routes.PatientFinance) { PatientFinanceRoute(deps) }
    composable(Routes.PatientCrm) { PatientCrmRoute(deps) }
    composable(Routes.PatientHistory) { PatientHistoryRoute(deps) }
    composable(Routes.PatientMessage) { PatientMessageRoute(deps) }
    composable(Routes.PatientNotes) { PatientNotesRoute(deps) }
    composable(Routes.HomeCareSend) { HomeCareSendRoute(deps) }
}

@Immutable
internal data class PatientFinanceUiState(
    val patientId: String,
    val patientName: String,
    val canBilling: Boolean,
    val plans: List<PlanFinanceUiState>,
    val invoices: List<InvoiceUiState>,
)

@Immutable
internal data class PlanFinanceUiState(
    val title: String,
    val progress: String,
    val agreedPrice: String,
    val received: String,
    val due: String,
    val depositApplied: String,
)

@Immutable
internal data class InvoiceUiState(
    val title: String,
    val subtitle: String,
    val canOpenCashier: Boolean,
)

@Immutable
internal data class PatientCrmUiState(
    val patientId: String,
    val notice: String,
    val source: String,
    val firstContact: String,
    val lastVisit: String,
    val lastContact: String,
    val tasks: List<CrmTaskUiState>,
    val activities: List<CrmActivityUiState>,
    val expectedDate: String,
    val expectedReason: String,
    val expectedSource: String,
)

@Immutable
internal data class CrmTaskUiState(val title: String, val subtitle: String)

@Immutable
internal data class CrmActivityUiState(val title: String, val subtitle: String)

@Immutable
internal data class PatientHistoryUiState(val events: List<HistoryEventUiState>)

@Immutable
internal data class HistoryEventUiState(val title: String, val subtitle: String, val icon: String)

@Immutable
internal data class PatientFormUiState(
    val patientId: String,
    val patientName: String,
    val alertsText: String = "",
    val photoConsent: Boolean = true,
    val homeCareText: String = "",
)

internal fun buildPatientFinanceState(
    state: ClinicState,
    patientId: String,
    canBilling: Boolean,
): PatientFinanceUiState {
    val patient = state.patient(patientId)
    val summary = state.careFinanceSummary(patientId)
    return PatientFinanceUiState(
        patientId = patient.id,
        patientName = patient.name,
        canBilling = canBilling,
        plans = summary.plans.map { row ->
            PlanFinanceUiState(
                title = "${row.plan.id} · ${row.plan.serviceName}",
                progress = "${row.plan.sessionsUsed}/${row.plan.sessionsTotal} buổi · ${if (row.plan.status == "active") "Đang thực hiện" else "Hoàn tất"}",
                agreedPrice = money(row.plan.agreedPrice),
                received = money(row.received + row.plan.depositApplied),
                due = money(row.due),
                depositApplied = money(row.plan.depositApplied),
            )
        },
        invoices = patient.invoices.map { invoice ->
            val received = if (invoice.paid) invoice.amount else invoice.received
            val due = invoice.amount - received
            InvoiceUiState(
                title = "${invoice.id} · ${viDate(invoice.date)}",
                subtitle = if (invoice.paid) {
                    "${invoice.label} · ${money(invoice.amount)} · Đã thanh toán"
                } else {
                    "${invoice.label} · còn ${money(due)}"
                },
                canOpenCashier = canBilling && !invoice.paid && due > 0,
            )
        },
    )
}

internal fun buildPatientCrmState(state: ClinicState, patientId: String): PatientCrmUiState {
    val patient = state.patient(patientId)
    val crm = patient.crm
    val nextAppointment = state.operations.appointments
        .filter { it.patient == patient.id && it.status !in setOf("cancelled", "missed", "completed") && it.date >= DAY }
        .sortedWith(compareBy({ it.date }, { it.time }))
        .firstOrNull()
    val expectedDate = nextAppointment?.date ?: crm.expectedNextVisitAt ?: crm.recommendationAt ?: DAY
    val source = if (nextAppointment != null) "appointment" else crm.expectedVisitSource.ifBlank { "doctor_recommendation" }
    val sourceLabel = crmSources[source] ?: "Chưa có nguồn"
    val lastOutcome = crm.latestOutcome?.let { crmOutcomes[it] } ?: "Chưa liên hệ"
    return PatientCrmUiState(
        patientId = patient.id,
        notice = "BƯỚC TIẾP THEO · Dự kiến quay lại ${viDate(expectedDate)}\n$sourceLabel · Phụ trách: ${crm.owner.ifBlank { "Chưa giao" }}",
        source = crm.source.ifBlank { "Chưa ghi nhận" },
        firstContact = viDate(crm.firstContactAt),
        lastVisit = viDate(crm.lastVisitAt ?: patient.lastVisit),
        lastContact = lastOutcome,
        tasks = state.crmQueue(allDates = true, patient = patient.id).map {
            CrmTaskUiState(it.reason, "${viDate(it.dueAt.take(10))} · ${it.owner}")
        },
        activities = state.crmActivities
            .filter { it.patientId == patient.id }
            .sortedByDescending { it.occurredAt }
            .map {
                CrmActivityUiState(
                    "${formatTimelineAt(it.occurredAt)} · ${it.channel}",
                    "${crmOutcomes[it.outcome] ?: it.outcome} · ${it.actor}",
                )
            },
        expectedDate = expectedDate,
        expectedReason = crm.expectedVisitReason.ifBlank { "Bác sĩ hẹn đánh giá" },
        expectedSource = if (source == "appointment") "doctor_recommendation" else source,
    )
}

internal fun buildPatientHistoryState(state: ClinicState, patientId: String): PatientHistoryUiState {
    val patient = state.patient(patientId)
    val rows = buildList {
        patient.events.forEach { event ->
            add(
                HistoryEvent(
                    at = event.date,
                    title = event.title,
                    detail = event.detail,
                    by = event.by,
                    kind = event.kind,
                ),
            )
        }
        state.operations.appointments
            .filter { it.patient == patient.id }
            .forEach { appointment ->
                val service = state.operations.services.find { it.id == appointment.service }?.name ?: appointment.service
                val status = mapOf(
                    "booked" to "Đặt hẹn",
                    "confirmed" to "Đã xác nhận",
                    "arrived" to "Đã đến",
                    "in_progress" to "Đang khám",
                    "completed" to "Hoàn tất",
                    "cancelled" to "Đã hủy",
                    "missed" to "Vắng hẹn",
                )[appointment.status] ?: appointment.status
                add(
                    HistoryEvent(
                        at = "${appointment.date}T${appointment.time}",
                        title = "Lịch hẹn · $status",
                        detail = service,
                        by = appointment.createdBy ?: "Lễ tân",
                        kind = "appointment",
                    ),
                )
            }
        state.crmActivities
            .filter { it.patientId == patient.id }
            .forEach { activity ->
                add(
                    HistoryEvent(
                        at = activity.occurredAt,
                        title = "${activity.channel} · ${crmOutcomes[activity.outcome] ?: activity.outcome}",
                        detail = activity.note,
                        by = activity.actor,
                        kind = "crm",
                    ),
                )
            }
        state.operations.payments
            .filter { it.patient == patient.id }
            .forEach { payment ->
                add(
                    HistoryEvent(
                        at = payment.at,
                        title = "Thu tiền · ${money(payment.amount)}",
                        detail = "${payment.invoice} · ${payment.method}",
                        by = "Thu ngân",
                        kind = "payment",
                    ),
                )
            }
    }.sortedByDescending { it.at }
    return PatientHistoryUiState(
        events = rows.map {
            HistoryEventUiState(
                title = "${formatTimelineAt(it.at)} · ${it.title}",
                subtitle = "${it.detail} · ${it.by}",
                icon = iconForHistoryKind(it.kind),
            )
        },
    )
}

internal fun buildPatientFormState(state: ClinicState, patientId: String): PatientFormUiState {
    val patient = state.patient(patientId)
    return PatientFormUiState(
        patientId = patient.id,
        patientName = patient.name,
        alertsText = patient.alerts.joinToString("\n"),
        photoConsent = patient.photoConsent,
        homeCareText = homeCareDraft(patient.aftercare, patient.meds.map { it.name }),
    )
}

internal fun homeCareDraft(aftercare: String, medicationNames: List<String>): String =
    medicationNames.takeIf { it.isNotEmpty() }?.joinToString("\n") ?: aftercare

@Composable
private fun PatientFinanceRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    PatientFinanceScreen(
        state = buildPatientFinanceState(
            state = clinic,
            patientId = deps.sessionStore.selectedPatientId(),
            canBilling = session.staffContext().can("billing"),
        ),
        onOpenCashier = { deps.navigator.go(Routes.CashierInvoices) },
    )
}

@Composable
internal fun PatientFinanceScreen(
    state: PatientFinanceUiState,
    onOpenCashier: () -> Unit,
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.PatientFinance)) {
        PemaHeading("Hóa đơn của ${state.patientName}", "Không suy ra hoàn tất điều trị từ thanh toán")
        state.plans.forEach { plan ->
            PemaInfoCard {
                PemaCardTitle(plan.title)
                PemaText(plan.progress, size = 12f, color = PemaColors.Muted)
                PemaCardLine("Giá chốt sau giảm", plan.agreedPrice)
                PemaCardLine("Đã thu", plan.received)
                PemaCardLine("Còn lại", plan.due)
                PemaCardLine("Tiền cọc đã phân bổ", plan.depositApplied)
            }
        }
        state.invoices.forEach { invoice ->
            PemaTile(
                title = invoice.title,
                sub = invoice.subtitle,
                icon = "receipt_long",
                onClick = if (invoice.canOpenCashier) onOpenCashier else null,
            )
        }
        if (state.canBilling) PemaPrimary("Mở thu ngân", onOpenCashier)
    }
}

@Composable
private fun PatientCrmRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val patientId = deps.sessionStore.selectedPatientId()
    val messenger = rememberPemaMessenger()
    PatientCrmScreen(
        state = buildPatientCrmState(clinic, patientId),
        canEditExpected = session.staffContext().can("crm"),
        onSetExpectedVisit = { date, reason, source ->
            runCommand(messenger) {
                deps.clinicStore.setExpectedVisit(patientId, date, reason, source, session.staffContext())
                messenger.show("Đã cập nhật ngày dự kiến")
            }
        },
    )
}

@Composable
internal fun PatientCrmScreen(
    state: PatientCrmUiState,
    canEditExpected: Boolean,
    onSetExpectedVisit: (String, String, String) -> Unit,
) {
    var showExpectedDialog by remember { mutableStateOf(false) }
    DetailScaffold(title = Routes.appBarTitleOf(Routes.PatientCrm)) {
        PemaNotice(state.notice)
        PemaInfoCard {
            PemaCardTitle("Bối cảnh chăm sóc")
            PemaCardLine("Nguồn khách", state.source)
            PemaCardLine("Tiếp xúc đầu tiên", state.firstContact)
            PemaCardLine("Khám gần nhất", state.lastVisit)
            PemaCardLine("CSKH gần nhất", state.lastContact)
        }
        PemaSection("Việc còn mở")
        if (state.tasks.isEmpty()) {
            PemaEmpty("Không còn việc CSKH mở.")
        } else {
            state.tasks.forEach { task ->
                PemaTile(task.title, task.subtitle, "task_alt", onClick = {})
            }
        }
        PemaSection("Lịch sử CSKH")
        if (state.activities.isEmpty()) {
            PemaEmpty("Chưa có hoạt động CSKH được ghi nhận")
        } else {
            state.activities.forEach { activity ->
                PemaTile(activity.title, activity.subtitle, "support_agent", onClick = null)
            }
        }
        PemaOutlinedButton(
            text = "Sửa ngày dự kiến",
            icon = "edit_calendar",
            onClick = { showExpectedDialog = true },
            enabled = canEditExpected,
        )
    }
    if (showExpectedDialog) {
        ExpectedVisitDialog(
            state = state,
            onDismiss = { showExpectedDialog = false },
            onConfirm = { date, reason, source ->
                showExpectedDialog = false
                onSetExpectedVisit(date, reason, source)
            },
        )
    }
}

@Composable
private fun ExpectedVisitDialog(
    state: PatientCrmUiState,
    onDismiss: () -> Unit,
    onConfirm: (String, String, String) -> Unit,
) {
    var date by remember(state.patientId) { mutableStateOf(state.expectedDate) }
    var reason by remember(state.patientId) { mutableStateOf(state.expectedReason) }
    val options = remember { crmSources.keys.filter { it != "appointment" } }
    var source by remember(state.patientId) { mutableStateOf(state.expectedSource.takeIf { it in options } ?: options.first()) }
    PemaDialog(
        title = "Ngày dự kiến quay lại",
        onDismiss = onDismiss,
        confirmText = "Lưu ngày dự kiến",
        onConfirm = { onConfirm(date, reason, source) },
        confirmEnabled = date.isNotBlank() && reason.isNotBlank(),
    ) {
        androidx.compose.foundation.layout.Column {
            PemaTextField(date, onValueChange = { date = it }, label = "Ngày bác sĩ/CSKH khuyến nghị")
            PemaTextField(reason, onValueChange = { reason = it }, label = "Lý do")
            PemaDropdownField(
                value = source,
                options = options,
                onSelected = { source = it },
                label = "Nguồn",
                display = { crmSources[it] ?: it },
            )
            PemaNotice("Nếu đã có lịch thực tế, Patient 360 ưu tiên ngày lịch đó. Khuyến nghị vẫn được giữ khi hủy lịch.")
        }
    }
}

@Composable
private fun PatientHistoryRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    PatientHistoryScreen(buildPatientHistoryState(clinic, deps.sessionStore.selectedPatientId()))
}

@Composable
internal fun PatientHistoryScreen(state: PatientHistoryUiState) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.PatientHistory)) {
        PemaHeading("Lịch sử hợp nhất", "Sự kiện gốc, người ghi nhận và liên kết công việc")
        state.events.forEach { event ->
            PemaTile(event.title, event.subtitle, event.icon, onClick = null)
        }
    }
}

@Composable
private fun PatientMessageRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val form = buildPatientFormState(clinic, deps.sessionStore.selectedPatientId())
    val messenger = rememberPemaMessenger()
    PatientMessageScreen(
        state = form,
        onSend = { text ->
            runCommand(messenger) {
                deps.clinicStore.sendPatientMessage(form.patientId, text, session.staffContext())
                messenger.show("Đã gửi tin nhắn")
                deps.navigator.back()
            }
        },
    )
}

@Composable
internal fun PatientMessageScreen(
    state: PatientFormUiState,
    onSend: (String) -> Unit,
) {
    var text by remember(state.patientId) { mutableStateOf("") }
    DetailScaffold(title = Routes.appBarTitleOf(Routes.PatientMessage)) {
        PemaNotice("Tin nhắn sẽ hiển thị trên Pema Care của ${state.patientName}. Không phải kênh cấp cứu.")
        PemaTextField(
            value = text,
            onValueChange = { text = it },
            label = "Nội dung",
            minLines = 5,
            maxLines = 5,
        )
        PemaPrimary("Gửi tin nhắn", if (text.trim().isEmpty()) null else { { onSend(text) } })
    }
}

@Composable
private fun PatientNotesRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val form = buildPatientFormState(clinic, deps.sessionStore.selectedPatientId())
    val messenger = rememberPemaMessenger()
    PatientNotesScreen(
        state = form,
        onSave = { alerts, consent ->
            runCommand(messenger) {
                deps.clinicStore.savePatientFacts(form.patientId, alerts, consent, session.staffContext())
                messenger.show("Đã lưu thông tin")
                deps.navigator.back()
            }
        },
    )
}

@Composable
internal fun PatientNotesScreen(
    state: PatientFormUiState,
    onSave: (String, Boolean) -> Unit,
) {
    var alerts by remember(state.patientId) { mutableStateOf(state.alertsText) }
    var photoConsent by remember(state.patientId) { mutableStateOf(state.photoConsent) }
    DetailScaffold(title = Routes.appBarTitleOf(Routes.PatientNotes)) {
        PemaTextField(
            value = alerts,
            onValueChange = { alerts = it },
            label = "Cảnh báo · mỗi dòng một mục",
            minLines = 2,
            maxLines = 2,
        )
        PemaCheckRow("Có đồng ý sử dụng ảnh chăm sóc", photoConsent, onCheckedChange = { photoConsent = it })
        PemaPrimary("Lưu thông tin", onClick = { onSave(alerts, photoConsent) })
    }
}

@Composable
private fun HomeCareSendRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val form = buildPatientFormState(clinic, deps.sessionStore.selectedPatientId())
    val messenger = rememberPemaMessenger()
    HomeCareSendScreen(
        state = form,
        onSend = { text ->
            runCommand(messenger) {
                deps.clinicStore.saveHomeCareInstructions(form.patientId, text, session.staffContext())
                messenger.show("Đã gửi hướng dẫn vào patient app")
                deps.navigator.back()
            }
        },
    )
}

@Composable
internal fun HomeCareSendScreen(
    state: PatientFormUiState,
    onSend: (String) -> Unit,
) {
    var text by remember(state.patientId) { mutableStateOf(state.homeCareText) }
    DetailScaffold(title = Routes.appBarTitleOf(Routes.HomeCareSend)) {
        PemaNotice("Hướng dẫn đã duyệt mới xuất hiện ở Chăm sóc tại nhà của người bệnh.")
        PemaTextField(
            value = text,
            onValueChange = { text = it },
            label = "Hướng dẫn cho người bệnh",
            minLines = 4,
            maxLines = 4,
        )
        PemaPrimary("Duyệt & gửi Pema Care", if (text.trim().isEmpty()) null else { { onSend(text) } })
    }
}

private fun runCommand(messenger: com.pema.clinic.core.ui.widgets.PemaMessenger, block: () -> Unit) {
    try {
        block()
    } catch (error: Throwable) {
        messenger.show(error.message ?: "Không lưu được thay đổi")
    }
}

private data class HistoryEvent(
    val at: String,
    val title: String,
    val detail: String,
    val by: String,
    val kind: String,
)

private fun formatTimelineAt(value: String): String {
    val date = viDate(value.take(10))
    val time = if (value.length >= 16 && value[10] == 'T') value.substring(11, 16) else ""
    return if (time.isBlank()) date else "$date $time"
}

private fun iconForHistoryKind(kind: String): String = when (kind) {
    "appointment", "event" -> "event"
    "followup", "crm", "message" -> "chat_bubble"
    "session" -> "medical_services"
    "photo" -> "photo_camera"
    "plan", "care" -> "route"
    "payment" -> "receipt_long"
    else -> "task_alt"
}

private fun ClinicState.patient(patientId: String) = patients.first { it.id == patientId }
