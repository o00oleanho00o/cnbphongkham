package com.pema.clinic.shared.care

import androidx.compose.runtime.Immutable
import com.pema.clinic.shared.catalog.CatalogRepository
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.patients.PatientsStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Contact status of a case before staff has logged anything. */
const val careNotContacted: String = "Chưa liên hệ"

/** Backward-compatible alias for earlier KMP feature code. */
const val CareNotContacted: String = careNotContacted

/** Care groups used by the compact CSKH queue filter sheet, in Flutter order. */
val careGroups: Map<String, String> = linkedMapOf(
    "d1" to "Sau thủ thuật · D+1",
    "d3" to "Ảnh tiến triển · D+3",
    "d7" to "Bác sĩ review · D+7",
    "due" to "Đến hạn tái khám",
    "overdue" to "Quá hạn tái khám",
    "no_show" to "Vắng hẹn",
    "abandoned" to "Tiếp tục liệu trình",
    "dormant90" to "Kết nối lại · 90 ngày",
    "dormant180" to "Kết nối lại · 180 ngày",
    "birthday" to "Sinh nhật trong tuần",
)

/** Status buckets used by the CSKH queue, in Flutter order. */
val careBuckets: Map<String, String> = linkedMapOf(
    careNotContacted to "Cần làm",
    "Đã liên hệ" to "Đã liên hệ",
    "Chờ bác sĩ" to "Chờ bác sĩ",
)

/** One profile in the CSKH queue together with its current contact status. */
@Immutable
data class CareCase(
    val profile: PatientProfile,
    val status: String = careNotContacted,
) {
    fun inGroup(group: String): Boolean = group == "all" || profile.careGroup == group

    fun matches(query: String): Boolean = "${profile.id} ${profile.name}".lowercase().contains(query)
}

@Immutable
data class CareQueueFilter(
    val group: String = "all",
    val query: String = "",
    val bucket: String = careNotContacted,
)

/** Profiles in the CSKH queue with their contact status. */
class CareQueue(
    private val catalog: CatalogRepository,
    private val patients: PatientsStore,
    scope: CoroutineScope,
) {
    private val mutableState = MutableStateFlow(buildCases())
    val state: StateFlow<List<CareCase>> = mutableState.asStateFlow()

    init {
        scope.launch {
            patients.state.collect { mutableState.value = buildCases() }
        }
    }

    fun cases(): List<CareCase> = state.value

    fun rows(filter: CareQueueFilter): List<PatientProfile> = state.value.mapNotNull { case ->
        if (case.status == filter.bucket && case.inGroup(filter.group) && case.matches(filter.query)) case.profile else null
    }

    fun groupCount(group: String): Int = state.value.count { it.inGroup(group) }

    fun bucketCount(bucket: String): Int = state.value.count { it.status == bucket }

    fun titleForBucket(bucket: String): String = if (bucket == careNotContacted) "Danh sách cần chăm sóc" else bucket

    fun rowCountLabel(count: Int): String = "$count khách"

    private fun buildCases(): List<CareCase> = catalog.catalog().profiles.mapNotNull { profile ->
        if (profile.inCareQueue) CareCase(profile = profile, status = statusOf(profile.id)) else null
    }

    fun statusOf(patientId: String): String = patients.of(patientId).careStatus
}
