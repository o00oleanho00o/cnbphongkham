package com.pema.clinic.shared.clinic

/** Validates an appointment with exact web prototype error messages. */
fun ClinicStore.validate(appointment: Appointment): Boolean = state.value.validate(appointment)

/** Validates an appointment with exact web prototype error messages. */
fun ClinicState.validate(appointment: Appointment): Boolean {
    val service = operations.services.find { it.id == appointment.service }
    val doctor = operations.doctors.find { it.id == appointment.doctor }
    val room = operations.rooms.find { it.id == appointment.room }
    val start = minutes(appointment.time)
    if (patients.none { it.id == appointment.patient } || service == null || doctor == null || room == null) {
        throw ClinicError("Hãy chọn bệnh nhân, dịch vụ, bác sĩ và phòng.")
    }
    if (appointment.room !in service.rooms) throw ClinicError("Phòng không phù hợp với dịch vụ đã chọn.")
    if (!service.active || !room.active) throw ClinicError("Dịch vụ hoặc phòng đang tạm ngưng.")
    if (!dateOk(appointment.date) || appointment.date < DAY || start == null || appointment.duration < 15 || appointment.duration > 180 || appointment.buffer < 0 || appointment.buffer > 60) {
        throw ClinicError("Ngày, giờ hoặc thời lượng không hợp lệ.")
    }
    val end = start + appointment.duration
    val occupied = end + appointment.buffer
    if (start < minutes(doctor.start)!! || occupied > minutes(doctor.end)!! || (start < minutes(doctor.breakEnd)!! && occupied > minutes(doctor.breakStart)!!)) {
        throw ClinicError("Ngoài ca bác sĩ hoặc trùng giờ nghỉ 12:00–13:00.")
    }
    for (block in operations.blocks.filter { it.date == appointment.date && (it.room == appointment.room || it.doctor == appointment.doctor) }) {
        if (start < minutes(block.end)!! && occupied > minutes(block.start)!!) throw ClinicError("Trùng thời gian khóa: ${block.reason}")
    }
    for (other in operations.appointments.filter { it.id != appointment.id && it.date == appointment.date && it.isActive() }) {
        val otherStart = minutes(other.time)!!
        val otherEnd = otherStart + other.duration
        val otherOccupied = otherEnd + other.buffer
        if (start < otherEnd && end > otherStart && (other.doctor == appointment.doctor || other.patient == appointment.patient)) {
            throw ClinicError("Trùng ${if (other.patient == appointment.patient) "bệnh nhân" else "bác sĩ"} với lịch ${other.time} của ${patient(other.patient).name}.")
        }
        if (other.room == appointment.room && start < otherOccupied && occupied > otherStart) {
            throw ClinicError("Phòng đang bận hoặc đang chuẩn bị sau lịch ${other.time}.")
        }
    }
    return true
}

/** Saves or moves an appointment, then syncs patient reception fields, CRM and audit. */
fun ClinicStore.saveAppointment(input: AppointmentInput, staff: StaffContext = StaffContext()): Appointment {
    staff.assertCan("booking")
    if (staff.role == "doctor" && input.doctor != staff.doctorId) throw ClinicError("Chỉ xếp lịch cho bác sĩ đang đăng nhập demo.")
    return transact { state ->
        val old = input.id?.let { state.operations.appointments.find { a -> a.id == it } }
        if (old != null && !old.isActive()) throw ClinicError("Lịch đã hủy/vắng hẹn; hãy tạo lịch mới.")
        val service = state.operations.services.find { it.id == input.service }
        val appointment = Appointment(
            id = old?.id ?: state.nextId("A"),
            patient = input.patient,
            doctor = input.doctor,
            room = input.room,
            service = input.service,
            date = input.date,
            time = input.time,
            duration = if (old != null && old.service == input.service) old.duration else input.duration ?: service?.duration ?: 0,
            buffer = if (old != null && old.service == input.service) old.buffer else input.buffer ?: service?.buffer ?: 0,
            price = if (old != null && old.service == input.service) old.price else input.price ?: service?.price ?: 0,
            status = old?.status ?: input.status ?: "booked",
            note = input.note,
            createdBy = old?.createdBy ?: "Lễ tân",
        )
        state.validate(appointment)
        if (input.crmTaskId != null && input.crmInput != null) state.bookingGuard(input.crmTaskId, input.crmInput, appointment.patient)
        val previousPatient = old?.patient
        var appointments = if (old != null) {
            state.operations.appointments.map { if (it.id == old.id) appointment else it }
        } else {
            state.operations.appointments + appointment
        }
        var waitlist = state.operations.waitlist
        if (input.waitlist != null) waitlist = waitlist.map { if (it.id == input.waitlist) it.copy(status = "scheduled") else it }
        var next = state.copy(operations = state.operations.copy(appointments = appointments, waitlist = waitlist))
            .sync(appointment.patient)
        if (previousPatient != null && previousPatient != appointment.patient) next = next.sync(previousPatient)
        val serviceName = next.operations.services.find { it.id == appointment.service }?.name.orEmpty()
        next = next
            .addEvent(appointment.patient, "appointment", if (old != null) "Đã dời lịch hẹn" else "Đã đặt lịch hẹn", "${appointment.date} · ${appointment.time} · $serviceName", "Lễ tân", appointment.date)
            .log(if (old != null) "Dời lịch" else "Đặt lịch", appointment.patient)
        next = if (input.crmTaskId != null && input.crmInput != null) next.markCrmBooked(input.crmTaskId, input.crmInput, appointment) else next.deriveCrmTasks(next.crmTasks)
        next to appointment
    }
}

/** Sets an appointment to `confirmed` or `arrived`. */
fun ClinicStore.setStatus(id: String, status: String): Unit = transact { state ->
    val appointment = state.operations.appointments.find { it.id == id }
    if (appointment == null || !appointment.isActive() || status !in setOf("confirmed", "arrived")) throw ClinicError("Không thể chuyển trạng thái lịch này.")
    var next = state.copy(operations = state.operations.copy(appointments = state.operations.appointments.map { if (it.id == id) it.copy(status = status) else it }))
    val p = next.patient(appointment.patient)
    if (status == "arrived" && appointment.date == DAY) {
        next = next.updatePatient(p.id) { patient ->
            patient.copy(
                status = "Đang chờ",
                crm = if (patient.crm.reactivationPending) patient.crm.copy(reactivatedAt = "${DAY}T09:00:00+07:00", reactivationPending = false) else patient.crm,
            )
        }
    }
    next = next.addEvent(p.id, "reception", if (status == "arrived") "Đã check-in lịch hẹn" else "Đã xác nhận lịch hẹn", "${appointment.date} · ${appointment.time}", "Lễ tân", appointment.date)
        .log("Cập nhật trạng thái lịch", p.id)
        .deriveCrmTasks(next.crmTasks)
    next to Unit
}

/** Cancels an active appointment with a required reason. */
fun ClinicStore.cancel(id: String, reason: String): Unit = transact { state ->
    val appointment = state.operations.appointments.find { it.id == id }
    if (appointment == null || !appointment.isActive() || reason.trim().isEmpty()) throw ClinicError("Cần lý do hủy cho lịch đang hoạt động.")
    var next = state.copy(
        operations = state.operations.copy(
            appointments = state.operations.appointments.map {
                if (it.id == id) it.copy(status = "cancelled", cancelledAt = "${DAY}T09:00:00+07:00", cancelReason = reason.trim()) else it
            },
        ),
    ).sync(appointment.patient)
    next = next.addEvent(appointment.patient, "appointment", "Đã hủy lịch hẹn", "${appointment.date} ${appointment.time} · ${reason.trim()}", "Lễ tân", appointment.date)
        .log("Hủy lịch", appointment.patient)
        .deriveCrmTasks(next.crmTasks)
    next to Unit
}

/** Records a payment against an invoice. */
fun ClinicStore.pay(patient: String, invoice: String, amount: Int, method: String, staff: StaffContext = StaffContext()): Unit {
    staff.assertCan("billing")
    transact { state ->
        val p = state.patient(patient)
        val inv = p.invoices.find { it.id == invoice } ?: throw ClinicError("Không tìm thấy hóa đơn.")
        val paid = if (inv.paid) inv.amount else inv.received
        val due = inv.amount - paid
        if (amount <= 0 || amount > due) throw ClinicError("Số tiền phải lớn hơn 0 và không vượt số còn lại.")
        if (method !in setOf("Tiền mặt", "Chuyển khoản")) throw ClinicError("Phương thức không hợp lệ.")
        val updated = inv.copy(received = paid + amount, paid = paid + amount == inv.amount)
        val next = state.updatePatient(patient) { patientState ->
            patientState.copy(invoices = patientState.invoices.map { if (it.id == invoice) updated else it })
        }.copy(
            operations = state.operations.copy(
                payments = listOf(Payment(state.nextId("PT"), patient, invoice, amount, method, "${DAY}T09:00:00+07:00")) + state.operations.payments,
            ),
        ).log("Thu tiền demo", patient)
        next to Unit
    }
}

/** Edits a service definition. */
fun ClinicStore.updateService(id: String, input: ServiceUpdate, staff: StaffContext = StaffContext()): Unit {
    staff.assertCan("config")
    transact { state ->
        val service = state.operations.services.find { it.id == id }
        if (service == null || input.name.trim().isEmpty() || input.duration !in 15..180 || input.buffer !in 0..60 || input.price < 0) {
            throw ClinicError("Kiểm tra tên, thời lượng 15–180 phút, đệm 0–60 phút và giá không âm.")
        }
        val next = state.copy(
            operations = state.operations.copy(
                services = state.operations.services.map {
                    if (it.id == id) it.copy(name = input.name, duration = input.duration, buffer = input.buffer, price = input.price, active = input.active, rooms = input.rooms) else it
                },
            ),
        ).log("Sửa dịch vụ", id)
        next to Unit
    }
}

/** Creates a room block after rejecting invalid ranges and overlaps. */
fun ClinicStore.block(input: RoomBlock, staff: StaffContext = StaffContext()): Unit {
    staff.assertCan("config")
    transact { state ->
        val start = minutes(input.start)
        val end = minutes(input.end)
        if (!dateOk(input.date) || state.operations.rooms.none { it.id == input.room } || input.reason.trim().isEmpty() || start == null || end == null || start < 480 || end > 1080 || start >= end) {
            throw ClinicError("Khoảng khóa phải hợp lệ trong 08:00–18:00 và có lý do.")
        }
        if (state.operations.appointments.any { it.isActive() && it.date == input.date && it.room == input.room && minutes(it.time)!! < end && minutes(it.time)!! + it.duration + it.buffer > start }) {
            throw ClinicError("Có lịch hẹn trong khoảng này. Hãy dời lịch trước khi khóa phòng.")
        }
        val block = input.copy(id = if (input.id.isBlank()) state.nextId("B") else input.id, reason = input.reason.trim())
        val next = state.copy(operations = state.operations.copy(blocks = state.operations.blocks + block)).log("Khóa phòng", input.room)
        next to Unit
    }
}

/** Synchronizes a patient's next/date/time/doctor fields from active future appointments. */
fun ClinicState.sync(patientId: String): ClinicState {
    val nextAppointment = operations.appointments
        .filter { it.patient == patientId && it.isActive() && it.status != "completed" && it.date >= DAY }
        .sortedWith(compareBy<Appointment> { it.date }.thenBy { it.time })
        .firstOrNull()
    return updatePatient(patientId) { patient ->
        patient.copy(
            next = nextAppointment?.date,
            time = nextAppointment?.time ?: "",
            doctor = nextAppointment?.let { a -> operations.doctors.find { it.id == a.doctor }?.name } ?: patient.doctor,
        )
    }
}

internal fun ClinicState.nextId(prefix: String): String {
    val used = buildSet {
        addAll(operations.appointments.map { it.id })
        addAll(operations.payments.map { it.id })
        addAll(operations.blocks.map { it.id })
        addAll(crmActivities.map { it.id })
    }
    var i = 1
    while ("$prefix-$i" in used) i++
    return "$prefix-$i"
}
