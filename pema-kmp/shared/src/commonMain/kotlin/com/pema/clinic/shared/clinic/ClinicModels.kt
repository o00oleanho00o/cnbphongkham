package com.pema.clinic.shared.clinic

import androidx.compose.runtime.Immutable

/** Root immutable state for the web-clinic domain port. */
@Immutable
data class ClinicState(
    val version: Int = 2,
    val selected: String = "P001",
    val patients: List<ClinicPatient> = emptyList(),
    val followups: List<FollowUp> = emptyList(),
    val operations: ClinicOperations = ClinicOperations(),
    val crmTasks: List<CrmTask> = emptyList(),
    val crmActivities: List<CrmActivity> = emptyList(),
    val crmAutomationRules: List<CrmRule> = emptyList(),
    val crmSegments: List<String> = emptyList(),
    val crmSequence: Int = 0,
    val audit: List<AuditEntry> = emptyList(),
)

/** Synthetic patient record mirroring `Pema.state.patients[]`. */
@Immutable
data class ClinicPatient(
    val id: String,
    val name: String,
    val age: Int,
    val gender: String,
    val phone: String,
    val concern: String,
    val plan: String,
    val procedure: String,
    val total: Int,
    val completed: Int,
    val doctor: String,
    val lastVisit: String?,
    val next: String?,
    val time: String,
    val status: String,
    val alerts: List<String>,
    val consent: Boolean,
    val photoConsent: Boolean,
    val aftercare: String,
    val meds: List<Medication>,
    val notes: String,
    val events: List<PatientEvent>,
    val messages: List<PatientMessage>,
    val sessions: List<TreatmentSessionRecord>,
    val invoices: List<Invoice>,
    val crm: CrmInfo = CrmInfo(),
    val servicePlans: List<ServicePlan> = emptyList(),
    val prescriptions: List<Prescription> = emptyList(),
    val depositLedger: List<DepositEntry> = emptyList(),
    val clinical: ClinicalNote? = null,
)

/** Medication/instruction row shown on Patient 360. */
@Immutable
data class Medication(val name: String, val use: String)

/** Timeline event stored on a patient. */
@Immutable
data class PatientEvent(
    val id: String,
    val kind: String,
    val date: String,
    val title: String,
    val detail: String,
    val by: String,
)

/** Patient-facing or clinic message. */
@Immutable
data class PatientMessage(val from: String, val text: String, val date: String)

/** Treatment session/visit record. */
@Immutable
data class TreatmentSessionRecord(
    val id: String,
    val date: String,
    val type: String,
    val note: String = "",
    val reviewed: Boolean = true,
    val view: String = "",
    val region: String = "",
    val image: String = "",
    val aftercare: String = "",
    val protocolId: String? = null,
)

/** Invoice ledger row. */
@Immutable
data class Invoice(
    val id: String,
    val date: String,
    val label: String,
    val amount: Int,
    val received: Int = 0,
    val paid: Boolean = false,
    val planId: String? = null,
) {
    /** Remaining unpaid amount using the web ledger semantics. */
    val due: Int get() = amount - if (paid) amount else received
}

/** Follow-up inbox item. */
@Immutable
data class FollowUp(
    val id: String,
    val patient: String,
    val type: String,
    val priority: String,
    val symptom: String,
    val date: String,
    val image: String?,
    val status: String,
    val owner: String,
    val crmActivityId: String? = null,
)

/** Operations state: doctors, rooms, services, appointments, waitlist, payments and blocks. */
@Immutable
data class ClinicOperations(
    val version: Int = 1,
    val doctors: List<Doctor> = emptyList(),
    val rooms: List<Room> = emptyList(),
    val services: List<Service> = emptyList(),
    val appointments: List<Appointment> = emptyList(),
    val waitlist: List<WaitlistEntry> = emptyList(),
    val payments: List<Payment> = emptyList(),
    val blocks: List<RoomBlock> = emptyList(),
)

/** Doctor resource with a fixed demo shift. */
@Immutable
data class Doctor(
    val id: String,
    val name: String,
    val start: String,
    val end: String,
    val breakStart: String,
    val breakEnd: String,
)

/** Room resource. */
@Immutable
data class Room(val id: String, val name: String, val active: Boolean = true)

/** Service/resource catalogue row. */
@Immutable
data class Service(
    val id: String,
    val name: String,
    val duration: Int,
    val buffer: Int,
    val price: Int,
    val active: Boolean = true,
    val rooms: List<String>,
)

/** Appointment row. Status values are the original web strings. */
@Immutable
data class Appointment(
    val id: String,
    val patient: String,
    val doctor: String,
    val room: String,
    val service: String,
    val date: String,
    val time: String,
    val duration: Int,
    val buffer: Int,
    val price: Int,
    val status: String,
    val note: String = "",
    val createdBy: String? = null,
    val cancelledAt: String? = null,
    val cancelReason: String? = null,
    val missedAt: String? = null,
)

/** Room/doctor block used by the operations schedule. */
@Immutable
data class RoomBlock(
    val id: String,
    val room: String,
    val doctor: String = "",
    val date: String,
    val start: String,
    val end: String,
    val reason: String,
)

/** Payment receipt pushed by the cashier command. */
@Immutable
data class Payment(
    val id: String,
    val patient: String,
    val invoice: String,
    val amount: Int,
    val method: String,
    val at: String,
)

/** Waitlist row used when scheduling from reception. */
@Immutable
data class WaitlistEntry(
    val id: String,
    val patient: String,
    val service: String,
    val note: String,
    val status: String,
)

/** CRM metadata stored on each patient. */
@Immutable
data class CrmInfo(
    val source: String = "",
    val owner: String = "",
    val firstContactAt: String? = null,
    val recommendationAt: String? = null,
    val expectedVisitReason: String = "",
    val expectedVisitSource: String = "",
    val marketingOptOut: Boolean = false,
    val demoCase: String = "",
    val demoGroup: String = "",
    val birthday: String? = null,
    val expectedNextVisitAt: String? = null,
    val overdueDays: Int = 0,
    val lifecycleStage: String = "new",
    val riskLevel: String = "normal",
    val lastVisitAt: String? = null,
    val lastProtocolSession: String? = null,
    val lastContactAt: String? = null,
    val latestOutcome: String? = null,
    val nextActionAt: String? = null,
    val nextActionType: String? = null,
    val bookedAfterCareAt: String? = null,
    val reactivationPending: Boolean = false,
    val reactivatedAt: String? = null,
)

/** CRM automation task derived from rules and patient state. */
@Immutable
data class CrmTask(
    val id: String,
    val patientId: String,
    val ruleId: String,
    val type: String,
    val reason: String,
    val priority: String,
    val createdAt: String,
    val dueAt: String,
    val status: String,
    val owner: String,
    val suggestedAction: String,
    val sourceEventId: String,
    val relatedAppointmentId: String? = null,
    val relatedPlanId: String? = null,
    val resolution: String? = null,
    val resolvedAt: String? = null,
)

/** CRM activity/outcome row. */
@Immutable
data class CrmActivity(
    val id: String,
    val patientId: String,
    val taskId: String,
    val type: String,
    val channel: String,
    val outcome: String,
    val note: String,
    val actor: String,
    val occurredAt: String,
    val nextActionAt: String? = null,
    val relatedAppointmentId: String? = null,
)

/** CRM automation rule. */
@Immutable
data class CrmRule(
    val id: String,
    val name: String,
    val trigger: String,
    val delayDays: Int,
    val suggestedAction: String,
    val priority: String,
    val active: Boolean = true,
    val actionType: String = "staff_task",
    val conditions: CrmRuleConditions = CrmRuleConditions(),
)

/** Rule condition subset used by the web automation. */
@Immutable
data class CrmRuleConditions(val protocol: String? = null, val marketing: Boolean = false)

/** Patient service plan linked to invoices and deposits. */
@Immutable
data class ServicePlan(
    val id: String,
    val serviceId: String,
    val serviceName: String,
    val sessionsTotal: Int,
    val sessionsUsed: Int,
    val listPrice: Int,
    val discount: Int,
    val agreedPrice: Int,
    val depositApplied: Int,
    val status: String,
    val startedAt: String,
    val doctor: String,
    val invoiceIds: List<String>,
    val economics: PlanEconomics? = null,
)

/** Optional economics fields used by CRM/finance panels. */
@Immutable
data class PlanEconomics(
    val consultant: String? = null,
    val doctor: String,
    val technician: String? = null,
    val serviceValue: Int,
    val commissionRuleId: String? = null,
    val consumables: List<String> = emptyList(),
)

/** Prescription header and item list. */
@Immutable
data class Prescription(
    val id: String,
    val status: String,
    val prescribedAt: String,
    val doctor: String,
    val indication: String,
    val items: List<PrescriptionItem>,
    val reviewedBy: String? = null,
    val reviewedAt: String? = null,
)

/** Prescription line. */
@Immutable
data class PrescriptionItem(
    val name: String,
    val dose: String,
    val frequency: String,
    val duration: String,
    val quantity: Int,
    val unit: String,
)

/** Deposit ledger row. */
@Immutable
data class DepositEntry(val id: String, val received: Int, val applied: Int, val date: String, val method: String)

/** Doctor-authored clinical note in CRM. */
@Immutable
data class ClinicalNote(val history: String, val diagnosis: String, val reviewedBy: String, val at: String)

/** Audit entry produced by state-changing commands. */
@Immutable
data class AuditEntry(val action: String, val patient: String, val at: String, val actor: String = "Tài khoản demo")

/** Result row for plan finance projections. */
@Immutable
data class ServicePlanFinance(val plan: ServicePlan, val received: Int, val due: Int)

/** Patient-level finance summary. */
@Immutable
data class CareFinanceSummary(
    val patientId: String,
    val plans: List<ServicePlanFinance>,
    val depositAllocated: Int,
    val depositUnallocated: Int,
    val prescriptions: List<Prescription>,
)

/** Appointment save payload with optional waitlist and CRM hooks. */
@Immutable
data class AppointmentInput(
    val id: String? = null,
    val patient: String,
    val doctor: String,
    val room: String,
    val service: String,
    val date: String,
    val time: String,
    val duration: Int? = null,
    val buffer: Int? = null,
    val price: Int? = null,
    val status: String? = null,
    val note: String = "Lịch giả lập để thử điều phối",
    val waitlist: String? = null,
    val crmTaskId: String? = null,
    val crmInput: CrmInput? = null,
)

/** CRM activity form payload. */
@Immutable
data class CrmInput(
    val channel: String,
    val outcome: String,
    val owner: String,
    val note: String,
    val nextActionAt: String? = null,
    val nextActionType: String? = null,
    val priority: String? = null,
)

/** Service edit payload. */
@Immutable
data class ServiceUpdate(
    val name: String,
    val duration: Int,
    val buffer: Int,
    val price: Int,
    val active: Boolean,
    val rooms: List<String>,
)

/** Staff demo account context and capability checks. */
@Immutable
data class StaffContext(
    val role: String = "owner",
    val name: String = "BS. Tâm",
    val doctorId: String? = "D0",
    val doctorName: String? = "BS. Tâm",
    val careOwner: String? = null,
) {
    /** Returns whether the current role can perform [capability]. */
    fun can(capability: String): Boolean = when (capability) {
        "clinical" -> role in setOf("owner", "doctor")
        "crm" -> role in setOf("owner", "care", "doctor")
        "booking" -> role in setOf("owner", "care", "doctor")
        "billing" -> role in setOf("owner", "accountant")
        "config" -> role == "owner"
        "readFinance" -> role in setOf("owner", "accountant", "doctor")
        else -> false
    }

    /** Throws the web prototype permission error when [capability] is denied. */
    fun assertCan(capability: String) {
        if (!can(capability)) throw ClinicError("Tài khoản $name không có tác vụ này. Chuyển đúng không gian làm việc.")
    }

    /** Doctor ownership rule from `PemaStaff.owns(p)`. */
    fun owns(patient: ClinicPatient, state: ClinicState): Boolean =
        role != "doctor" ||
            patient.doctor == name ||
            state.operations.appointments.any {
                it.patient == patient.id && it.doctor == doctorId && it.status !in setOf("cancelled", "missed")
            }
}

/** Domain exception matching web command errors. */
class ClinicError(message: String) : Exception(message)
