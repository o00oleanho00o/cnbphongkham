package com.pema.clinic.shared.clinic

import com.pema.clinic.shared.session.Session

private val doctorIds = mapOf("BS. Tâm" to "D0", "BS. Mai" to "D1", "BS. An" to "D2", "BS. Lan" to "D3")

/**
 * Web `PemaStaff.current()` for the app workspace [Session] (demo switch, not RBAC).
 * Owner acts as BS. Tâm (D0) like the web `owner-tam` account; CSKH owners are "CSKH <name>".
 */
fun Session.staffContext(): StaffContext = when (staffRole) {
    "doctor" -> StaffContext(role = "doctor", name = staffDoctor, doctorId = doctorIds[staffDoctor], doctorName = staffDoctor)
    "care" -> StaffContext(role = "care", name = staffName, doctorId = null, doctorName = null, careOwner = "CSKH $staffName")
    "accountant" -> StaffContext(role = "accountant", name = staffName, doctorId = null, doctorName = null)
    else -> StaffContext(role = "owner", name = "BS. Tâm", doctorId = "D0", doctorName = "BS. Tâm")
}
