package com.pema.clinic.shared.util

import kotlin.math.roundToLong

fun money(value: Number): String {
    val rounded = value.toDouble().roundToLong()
    val sign = if (rounded < 0) "-" else ""
    val digits = rounded.toString().removePrefix("-")
    val grouped = digits.reversed().chunked(3).joinToString(".").reversed()
    return "$sign$grouped ₫"
}
