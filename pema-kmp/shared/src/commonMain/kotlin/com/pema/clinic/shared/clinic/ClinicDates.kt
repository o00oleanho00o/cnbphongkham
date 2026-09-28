package com.pema.clinic.shared.clinic

import com.pema.clinic.shared.util.money as sharedMoney

/** Fixed demo day used by the web prototype. */
const val DAY: String = "2026-09-20"

/** Adds [days] calendar days to an ISO date (`yyyy-MM-dd`). */
fun addDays(day: String, days: Int): String = civilFromDays(daysFromCivil(day) + days)

/** Returns whole calendar days from [from] to [to]. */
fun daysBetween(from: String, to: String = DAY): Int = daysFromCivil(to) - daysFromCivil(from)

/** Parses `HH:mm` to minutes from midnight, or `null` when invalid. */
fun minutes(value: String?): Int? {
    if (value == null || !Regex("""^([01]\d|2[0-3]):[0-5]\d$""").matches(value)) return null
    return value.take(2).toInt() * 60 + value.takeLast(2).toInt()
}

/** Formats minutes from midnight as `HH:mm`. */
fun time(minutes: Int): String =
    "${(minutes / 60).toString().padStart(2, '0')}:${(minutes % 60).toString().padStart(2, '0')}"

/** Vietnamese date format matching `toLocaleDateString('vi-VN')`, e.g. `20/9/2026`. */
fun viDate(day: String?): String {
    if (day.isNullOrBlank()) return "Chưa ghi nhận"
    val date = parseDateOrNull(day.take(10)) ?: return "Chưa ghi nhận"
    return "${date.day}/${date.month}/${date.year}"
}

/** Vietnamese money format used by the prototype, e.g. `1.200.000 ₫`. */
fun money(value: Number): String = sharedMoney(value)

/** Up to two initials from the last two name tokens. */
fun initials(name: String): String = name.trim().split(Regex("""\s+""")).takeLast(2).joinToString("") { it.first().toString() }

internal fun dateOk(day: String?): Boolean = day != null && parseDateOrNull(day) != null && day == civilFromDays(daysFromCivil(day))

private data class CivilDate(val year: Int, val month: Int, val day: Int)

private fun parseDateOrNull(value: String): CivilDate? {
    if (!Regex("""^\d{4}-\d{2}-\d{2}$""").matches(value)) return null
    val year = value.substring(0, 4).toInt()
    val month = value.substring(5, 7).toInt()
    val day = value.substring(8, 10).toInt()
    if (month !in 1..12) return null
    val maxDay = when (month) {
        1, 3, 5, 7, 8, 10, 12 -> 31
        4, 6, 9, 11 -> 30
        else -> if (isLeap(year)) 29 else 28
    }
    if (day !in 1..maxDay) return null
    return CivilDate(year, month, day)
}

private fun isLeap(year: Int): Boolean = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)

private fun daysFromCivil(day: String): Int {
    val date = parseDateOrNull(day.take(10)) ?: error("Invalid ISO date: $day")
    var y = date.year
    val m = date.month
    val d = date.day
    y -= if (m <= 2) 1 else 0
    val era = floorDiv(y, 400)
    val yoe = y - era * 400
    val mp = m + if (m > 2) -3 else 9
    val doy = (153 * mp + 2) / 5 + d - 1
    val doe = yoe * 365 + yoe / 4 - yoe / 100 + doy
    return era * 146097 + doe - 719468
}

private fun civilFromDays(days: Int): String {
    var z = days + 719468
    val era = floorDiv(z, 146097)
    val doe = z - era * 146097
    val yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365
    var y = yoe + era * 400
    val doy = doe - (365 * yoe + yoe / 4 - yoe / 100)
    val mp = (5 * doy + 2) / 153
    val d = doy - (153 * mp + 2) / 5 + 1
    val m = mp + if (mp < 10) 3 else -9
    y += if (m <= 2) 1 else 0
    return "${y.toString().padStart(4, '0')}-${m.toString().padStart(2, '0')}-${d.toString().padStart(2, '0')}"
}

private fun floorDiv(a: Int, b: Int): Int {
    var result = a / b
    if ((a xor b) < 0 && result * b != a) result--
    return result
}
