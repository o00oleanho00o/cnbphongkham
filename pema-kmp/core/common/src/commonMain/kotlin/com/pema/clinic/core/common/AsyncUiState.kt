package com.pema.clinic.core.common

import androidx.compose.runtime.Immutable

@Immutable
data class AsyncUiState<out T>(
    val data: T? = null,
    val loading: Boolean = false,
    val error: String? = null,
) {
    val hasData: Boolean get() = data != null

    fun loading(): AsyncUiState<T> = copy(loading = true, error = null)
    fun success(value: @UnsafeVariance T): AsyncUiState<T> = AsyncUiState(data = value)
    fun failure(message: String): AsyncUiState<T> = copy(loading = false, error = message)

    companion object {
        fun <T> empty(): AsyncUiState<T> = AsyncUiState()
        fun <T> loading(previous: T? = null): AsyncUiState<T> = AsyncUiState(data = previous, loading = true)
        fun <T> success(value: T): AsyncUiState<T> = AsyncUiState(data = value)
    }
}
