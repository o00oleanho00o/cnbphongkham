package com.pema.clinic.core.common

data class ApiConfig(
    val financeApi: String = DEFAULT_FINANCE_API,
) {
    companion object {
        const val DEFAULT_FINANCE_API = "http://127.0.0.1:4174"
    }
}
