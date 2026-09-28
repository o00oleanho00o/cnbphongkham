package com.pema.clinic.shared.clinic

/** Patient summary text matching `Pema.brief(p)`. */
fun brief(state: ClinicState, patient: ClinicPatient): String {
    val open = state.followups.filter { it.patient == patient.id && it.status == "open" }
    val followup = patient.events.find { it.kind == "followup" }?.detail ?: "Chưa có cập nhật sau điều trị."
    val openText = if (open.isNotEmpty()) {
        "Có ${open.size} mục theo dõi chưa xử lý; cần kiểm tra trước buổi tiếp theo."
    } else {
        "Không có mục theo dõi đang mở."
    }
    return "${patient.name}, ${patient.age} tuổi, quay lại để đánh giá ${patient.concern.lowercase()}. " +
        "Đã hoàn tất ${patient.completed}/${patient.total} buổi của ${patient.plan.lowercase()}. " +
        "Lần gần nhất: ${viDate(patient.lastVisit)}. $followup $openText " +
        "Bước tiếp theo: bác sĩ đánh giá đáp ứng, xác nhận dữ liệu và quyết định kế hoạch."
}

/** Finance projection for the Patient 360 service/finance tab. */
fun ClinicState.careFinanceSummary(patientId: String): CareFinanceSummary {
    val p = patient(patientId)
    val plans = p.servicePlans.map { plan ->
        val received = plan.invoiceIds.sumOf { invoiceId ->
            p.invoices.find { it.id == invoiceId }?.let { if (it.paid) it.amount else it.received } ?: 0
        }
        ServicePlanFinance(plan, received, maxOf(0, plan.agreedPrice - received - plan.depositApplied))
    }
    val receivedDeposit = p.depositLedger.sumOf { it.received }
    val appliedDeposit = p.depositLedger.sumOf { it.applied }
    return CareFinanceSummary(p.id, plans, appliedDeposit, maxOf(0, receivedDeposit - appliedDeposit), p.prescriptions)
}
