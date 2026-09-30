package com.pema.clinic.shared.clinic

/**
 * Validates the CRM "Đồng ý đặt lịch" hand-off before the appointment form opens.
 *
 * The actual CRM task is completed by [saveAppointment] after a valid appointment is
 * saved with the same CRM task id and input.
 */
fun ClinicStore.prepareCrmBooking(
    taskId: String,
    input: CrmInput,
    patientId: String,
    staff: StaffContext = StaffContext(),
) {
    staff.assertCan("crm")
    state.value.bookingGuard(taskId, input, patientId)
    preparedCrmBookings.getOrPut(this) { mutableMapOf() }[taskId] = input
}

/** Returns the validated CRM booking hand-off input prepared before opening the booking form. */
fun ClinicStore.preparedCrmBookingInput(taskId: String): CrmInput? = preparedCrmBookings[this]?.get(taskId)

/** Clears a CRM booking hand-off after the appointment form successfully saves. */
fun ClinicStore.clearPreparedCrmBooking(taskId: String) {
    preparedCrmBookings[this]?.remove(taskId)
}

private val preparedCrmBookings = mutableMapOf<ClinicStore, MutableMap<String, CrmInput>>()
