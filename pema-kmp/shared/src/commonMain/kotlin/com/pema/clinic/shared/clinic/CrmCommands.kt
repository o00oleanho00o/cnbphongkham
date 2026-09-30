package com.pema.clinic.shared.clinic

/** CRM outcome labels from the web prototype. */
val crmOutcomes: Map<String, String> = mapOf(
    "unanswered" to "Không nghe máy",
    "callback" to "Gọi lại sau",
    "no_need" to "Đã liên hệ, chưa có nhu cầu",
    "busy" to "Đang bận, hẹn gọi lại",
    "booked" to "Đồng ý đặt lịch",
    "doctor" to "Muốn bác sĩ tư vấn",
    "reaction" to "Có phản hồi sau điều trị",
    "complaint" to "Khiếu nại",
    "optout" to "Không muốn nhận CSKH",
    "invalid" to "Sai số / không liên hệ được",
)

/** CRM expected-visit source labels. */
val crmSources: Map<String, String> = mapOf(
    "doctor_recommendation" to "Bác sĩ khuyến nghị",
    "service_protocol" to "Protocol dịch vụ",
    "treatment_plan" to "Kế hoạch điều trị",
    "appointment" to "Lịch đã đặt",
    "followup_automation" to "Chăm sóc sau điều trị",
)

/** CRM lifecycle labels. */
val crmStageLabels: Map<String, String> = mapOf(
    "new" to "Khách mới",
    "returning" to "Khách quay lại",
    "treating" to "Đang điều trị",
    "dormant" to "Lâu chưa quay lại",
    "reactivated" to "Đã quay lại sau CSKH",
)

/** Due CRM queue matching `PemaCRM.queue()`. */
fun ClinicState.crmQueue(
    allDates: Boolean = false,
    rule: String = "all",
    owner: String = "all",
    patient: String? = null,
): List<CrmTask> {
    fun rank(task: CrmTask): Int = if (task.type in setOf("d1", "d3", "d7")) 0 else 1
    fun priority(task: CrmTask): Int = mapOf("high" to 0, "normal" to 1, "low" to 2).getValue(task.priority)
    return crmTasks.filter { task ->
        task.status in setOf("open", "rescheduled") &&
            (allDates || task.dueAt.take(10) <= DAY || task.type == "birthday") &&
            (rule == "all" || task.type == rule) &&
            (owner == "all" || task.owner == owner) &&
            (patient == null || task.patientId == patient)
    }.sortedWith(compareBy<CrmTask> { rank(it) }.thenBy { priority(it) }.thenBy { it.dueAt })
}

/** Resolves or reschedules a CRM task by recording an activity. */
fun ClinicStore.resolveCrmTask(id: String, input: CrmInput, staff: StaffContext = StaffContext()): CrmActivity {
    staff.assertCan("crm")
    return transact { state ->
        val prepared = state.deriveCrmTasks(state.crmTasks)
        val task = prepared.crmTasks.find { it.id == id }
        prepared.validateCrm(task, input, staff, booking = false)
        val (next, activity) = prepared.finishCrm(task!!, input, staff, null)
        next to activity
    }
}

/** Sets a patient expected-visit date and reruns CRM automation. */
fun ClinicStore.setExpectedVisit(patientId: String, date: String, reason: String, source: String, staff: StaffContext = StaffContext()): Unit {
    staff.assertCan("crm")
    transact { state ->
        if (!dateOk(date) || reason.trim().isEmpty() || source !in crmSources.keys || source == "appointment") {
            throw ClinicError("Nhập ngày hợp lệ, lý do và nguồn khuyến nghị.")
        }
        val next = state.updatePatient(patientId) { p ->
            p.copy(crm = p.crm.copy(recommendationAt = date, expectedVisitReason = reason.trim(), expectedVisitSource = source))
        }.addEvent(patientId, "plan", "Ngày dự kiến tái khám", "$date · ${reason.trim()}", state.patient(patientId).doctor, DAY)
            .deriveCrmTasks(state.crmTasks)
        next to Unit
    }
}

/** Saves doctor clinical history/diagnosis from the CRM patient tab. */
fun ClinicStore.saveClinicalNote(patientId: String, history: String, diagnosis: String, staff: StaffContext = StaffContext()): Unit {
    staff.assertCan("clinical")
    transact { state ->
        val p = state.patient(patientId)
        if (!staff.owns(p, state)) throw ClinicError("Hồ sơ không thuộc bác sĩ phụ trách.")
        if (diagnosis.trim().isEmpty() || history.trim().isEmpty()) throw ClinicError("Nhập tiền sử và nhận định/chẩn đoán do bác sĩ xác nhận.")
        val next = state.updatePatient(patientId) {
            it.copy(clinical = ClinicalNote(history.trim(), diagnosis.trim(), it.doctor, DAY))
        }.addEvent(patientId, "consult", "Bác sĩ ghi nhận khám và chẩn đoán", diagnosis.trim(), p.doctor, DAY)
        next to Unit
    }
}

/** Reception state machine from `PemaCRM.reception`. */
fun ClinicStore.reception(id: String, status: String): Unit = transact { state ->
    val appointment = state.operations.appointments.find { it.id == id }
    if (appointment == null || appointment.date != DAY || !appointment.isActive()) throw ClinicError("Lịch không thể chuyển trạng thái.")
    val allowed = mapOf(
        "booked" to setOf("arrived", "missed"),
        "confirmed" to setOf("arrived", "missed"),
        "arrived" to setOf("in_progress"),
        "in_progress" to setOf("completed"),
    )
    if (status !in allowed[appointment.status].orEmpty()) throw ClinicError("Trạng thái không hợp lệ.")
    val updatedAppointment = appointment.copy(
        status = status,
        missedAt = if (status == "missed") "${DAY}T09:00:00+07:00" else appointment.missedAt,
    )
    var next = state.copy(operations = state.operations.copy(appointments = state.operations.appointments.map { if (it.id == id) updatedAppointment else it }))
    val patientStatus = mapOf("arrived" to "Đang chờ", "in_progress" to "Đang điều trị", "completed" to "Hoàn tất", "missed" to "Vắng hẹn").getValue(status)
    val patient = next.patient(appointment.patient)
    next = next.updatePatient(patient.id) { p ->
        p.copy(
            status = patientStatus,
            crm = if (status == "arrived" && p.crm.reactivationPending) p.crm.copy(reactivatedAt = nextCrmStamp(next), reactivationPending = false) else p.crm,
        )
    }.sync(patient.id)
        .addEvent(patient.id, "reception", "Tiếp đón: $patientStatus", "${appointment.date} ${appointment.time}", "Lễ tân", DAY)
        .deriveCrmTasks(next.crmTasks)
    next to Unit
}

internal fun ClinicState.bookingGuard(id: String, input: CrmInput, patientId: String) {
    val task = crmTasks.find { it.id == id }
    validateCrm(task, input, StaffContext(), booking = true)
    if (task!!.patientId != patientId) throw ClinicError("Lịch phải thuộc đúng bệnh nhân của task CSKH.")
}

internal fun ClinicState.markCrmBooked(id: String, input: CrmInput, appointment: Appointment): ClinicState {
    val task = crmTasks.find { it.id == id }
    val (next, _) = finishCrm(task!!, input, StaffContext(), appointment)
    return next
}

private fun ClinicState.finishCrm(task: CrmTask, input: CrmInput, staff: StaffContext, appointment: Appointment?): Pair<ClinicState, CrmActivity> {
    val patient = patient(task.patientId)
    val wasDormant = (patient.lastVisit?.let { daysBetween(it) } ?: 0) >= 90
    val sequence = crmSequence + 1
    val occurredAt = crmStamp(sequence)
    val activity = CrmActivity(
        id = "CA-$sequence",
        patientId = patient.id,
        taskId = task.id,
        type = if (input.outcome == "complaint") "complaint" else "cskh",
        channel = input.channel,
        outcome = input.outcome,
        note = input.note.trim(),
        actor = staff.careOwner ?: staff.name,
        occurredAt = occurredAt,
        nextActionAt = input.nextActionAt,
        relatedAppointmentId = appointment?.id,
    )
    var tasks = crmTasks.map {
        if (it.id == task.id) {
            it.copy(
                status = if (input.nextActionAt != null && appointment == null) "rescheduled" else "resolved",
                owner = input.owner,
                priority = input.priority ?: it.priority,
                resolution = input.outcome,
                resolvedAt = if (input.nextActionAt != null && appointment == null) null else occurredAt,
                dueAt = if (input.nextActionAt != null && appointment == null) "${input.nextActionAt}+07:00" else it.dueAt,
                relatedAppointmentId = appointment?.id ?: it.relatedAppointmentId,
            )
        } else it
    }
    var next = copy(crmSequence = sequence, crmActivities = listOf(activity) + crmActivities, crmTasks = tasks)
        .updatePatient(patient.id) { p ->
            p.copy(
                crm = p.crm.copy(
                    lastContactAt = occurredAt,
                    latestOutcome = input.outcome,
                    nextActionAt = input.nextActionAt,
                    nextActionType = input.nextActionType,
                    owner = input.owner,
                    bookedAfterCareAt = if (appointment != null) occurredAt else p.crm.bookedAfterCareAt,
                    reactivationPending = if (appointment != null) wasDormant else p.crm.reactivationPending,
                    marketingOptOut = if (input.outcome == "optout") true else p.crm.marketingOptOut,
                ),
            )
        }
        .log("CSKH · ${crmOutcomes.getValue(input.outcome)}", patient.id)
    if (input.outcome in setOf("doctor", "reaction", "complaint")) {
        next = next.copy(
            followups = listOf(
                FollowUp(
                    id = "CRM-F-${activity.id}",
                    patient = patient.id,
                    type = if (input.outcome == "complaint") "Khiếu nại cần xử lý" else "CSKH chuyển bác sĩ",
                    priority = "review",
                    symptom = input.note.trim(),
                    date = occurredAt,
                    status = "open",
                    owner = patient.doctor,
                    crmActivityId = activity.id,
                    image = null,
                ),
            ) + next.followups,
        )
    }
    tasks = next.crmTasks
    next = next.deriveCrmTasks(tasks)
    return next to activity
}

private fun ClinicState.validateCrm(task: CrmTask?, input: CrmInput, staff: StaffContext, booking: Boolean) {
    if (staff.role == "doctor" && (task == null || task.type != "d7" || !staff.owns(patient(task.patientId), this))) {
        throw ClinicError("Tài khoản bác sĩ chỉ xử lý review D+7 của hồ sơ phụ trách.")
    }
    if (task == null || task.status !in setOf("open", "rescheduled")) throw ClinicError("Việc đã được xử lý hoặc không còn hợp lệ. Tải lại danh sách.")
    if (input.outcome !in crmOutcomes.keys || input.channel !in setOf("Gọi điện", "Zalo", "SMS", "Ghi chú nội bộ") || input.owner.trim().isEmpty() || input.note.trim().isEmpty()) {
        throw ClinicError("Chọn kênh, kết quả, người phụ trách và nhập ghi chú.")
    }
    if (input.outcome == "booked" && !booking) throw ClinicError("Cần lưu lịch hẹn hợp lệ trước khi hoàn tất việc.")
    if (input.outcome in setOf("unanswered", "callback", "busy") && input.nextActionAt == null) throw ClinicError("Cần ngày giờ gọi lại.")
    val nextActionAt = input.nextActionAt
    if (nextActionAt != null && (!Regex("""^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$""").matches(nextActionAt) || nextActionAt <= "${DAY}T09:00")) {
        throw ClinicError("Bước tiếp theo phải sau 09:00 ngày demo, đúng ngày giờ.")
    }
}

private fun nextCrmStamp(state: ClinicState): String = crmStamp(state.crmSequence + 1)

private fun crmStamp(sequence: Int): String = "${DAY}T09:00:${sequence.toString().padStart(2, '0')}+07:00"
