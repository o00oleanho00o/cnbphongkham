package com.pema.clinic.shared.catalog

import androidx.compose.runtime.Immutable

/** A catalog item as supplied in the Excel export. */
@Immutable
data class Product(
    val id: String,
    val code: String,
    val name: String,
    val unit: String,
    /** Excel "loại" column, e.g. "Thuốc". */
    val sourceType: String,
    val price: Int,
    /** `PRESCRIPTION`, `CONSULTATION` or `UNRESOLVED` (needs classification). */
    val outputType: String,
) {
    val needsClassification: Boolean get() = outputType == "UNRESOLVED"

    /** Case-insensitive match on code or name; [query] must be lower-case. */
    fun matches(query: String): Boolean = "$code $name".lowercase().contains(query)
}

/** A CRM follow-up attached to a profile, e.g. `d7` or `due`. */
@Immutable
data class CareTask(
    val id: String,
    val type: String,
    val title: String,
    val status: String,
)

/** Synthetic patient profile from the bundled catalog. */
@Immutable
data class PatientProfile(
    val id: String,
    val name: String,
    val doctor: String,
    val sessions: Int,
    val totalSessions: Int,
    val appointment: String,
    val day: String,
    /** CSKH group key (`d1`, `due`, ...); empty when not in the care queue. */
    val careGroup: String,
    /** Human label of [careGroup] shown in account pickers. */
    val caseLabel: String,
    val tasks: List<CareTask> = emptyList(),
) {
    val inCareQueue: Boolean get() = careGroup.isNotEmpty()

    fun hasTask(type: String): Boolean = tasks.any { it.type == type }

    /** Case-insensitive match on name; [query] must be lower-case. */
    fun matches(query: String): Boolean = name.lowercase().contains(query)

    /** Up to two initials from the given names, e.g. "Nguyễn Minh Linh" → "ML". */
    val initials: String
        get() = name
            .split(' ')
            .drop(1)
            .asReversed()
            .take(2)
            .asReversed()
            .joinToString("") { it[0].toString() }
}

/** Bundled product catalog and synthetic patient profiles. Loaded once. */
@Immutable
class Catalog(
    val products: List<Product>,
    val profiles: List<PatientProfile>,
) {
    val patientIds: List<String> = profiles.map { it.id }
    private val indexById: Map<String, Int> = profiles.mapIndexed { index, profile -> profile.id to index }.toMap()

    fun profile(id: String): PatientProfile = profiles[indexById.getValue(id)]

    /** Position used by the session's patient selection. */
    fun indexOf(id: String): Int = indexById.getValue(id)

    override fun equals(other: Any?): Boolean =
        other is Catalog && products == other.products && profiles == other.profiles

    override fun hashCode(): Int = 31 * products.hashCode() + profiles.hashCode()

    override fun toString(): String = "Catalog(products=$products, profiles=$profiles)"
}
