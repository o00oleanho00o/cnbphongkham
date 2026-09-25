package com.pema.clinic.core.ui

fun moneyFormat(value: Int): String {
    val sign = if (value < 0) "-" else ""
    val digits = kotlin.math.abs(value).toString().reversed().chunked(3).joinToString(".").reversed()
    return "$sign$digits ₫"
}
