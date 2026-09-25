package com.pema.clinic.shared.finance

import com.pema.clinic.shared.session.Session
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** App-scoped finance state store mirroring Flutter's FinanceNotifier. */
class FinanceStore(
    private val repository: FinanceRepository,
    private val scope: CoroutineScope,
    initialState: FinanceState = FinanceState(),
    private val pollMillis: Long = 4_000,
) {
    private val mutableState = MutableStateFlow(initialState)
    val state: StateFlow<FinanceState> = mutableState.asStateFlow()

    private var timer: Job? = null
    private var generation = 0
    private var loading = false
    private var foreground = true

    /** Polls while the app is in the foreground. */
    fun start() {
        refreshInScope()
        if (timer == null) {
            timer = scope.launch {
                while (true) {
                    delay(pollMillis)
                    if (foreground && !loading && !state.value.sending) refresh()
                }
            }
        }
    }

    fun stop() {
        generation++
        timer?.cancel()
        timer = null
    }

    fun setForeground(value: Boolean) {
        foreground = value
        if (foreground) refreshInScope()
    }

    suspend fun refresh() {
        val token = ++generation
        loading = true
        try {
            val value = repository.getState(state.value.month, state.value.actor)
            if (token != generation) return
            mutableState.value = state.value.copy(data = value, error = "")
        } catch (_: Throwable) {
            if (token == generation) {
                mutableState.value = state.value.copy(
                    error = "Chưa kết nối dữ liệu tài chính. Kiểm tra dịch vụ và thử lại.",
                )
            }
        } finally {
            if (token == generation) loading = false
        }
    }

    /** Switching role drops the previous role's private projection first. */
    fun select(value: String) {
        val bits = value.split(':')
        generation++
        mutableState.value = state.value.copy(role = bits[0], doctor = bits[1], data = null)
        refreshInScope()
    }

    suspend fun setMonth(month: String) {
        mutableState.value = state.value.copy(month = month)
        refresh()
    }

    suspend fun approveEntry(id: String): Boolean = command { repository.approveEntry(id, it) }

    suspend fun voidEntry(id: String, reason: String): Boolean = command { repository.voidEntry(id, reason, it) }

    suspend fun recordEntry(entry: ProcedureEntry): Boolean = command { repository.recordEntry(entry, it) }

    suspend fun recordPayment(
        key: String,
        invoice: String,
        amount: Int,
        method: String = "Tiền mặt",
    ): Boolean = command { actor ->
        repository.recordPayment(key = key, invoice = invoice, amount = amount, method = method, actor = actor)
    }

    suspend fun closePeriod(): Boolean = command { repository.closePeriod(state.value.month, it) }

    suspend fun markPeriodPaid(reference: String): Boolean = command { repository.markPeriodPaid(state.value.month, reference, it) }

    suspend fun updateRate(service: String, rate: Int, basis: String): Boolean = command { actor ->
        repository.updateRate(service = service, rate = rate, basis = basis, actor = actor)
    }

    suspend fun markNotificationRead(id: String): Boolean = command { repository.markNotificationRead(id, it) }

    /** Runs one command at a time; on success reloads, on failure keeps the server message in state.error. */
    private suspend fun command(send: suspend (FinanceActor) -> Unit): Boolean {
        if (state.value.sending) return false
        mutableState.value = state.value.copy(sending = true)
        try {
            send(state.value.actor)
            mutableState.value = state.value.copy(error = "")
            refresh()
            return true
        } catch (e: Throwable) {
            mutableState.value = state.value.copy(error = cleanError(e))
            return false
        } finally {
            mutableState.value = state.value.copy(sending = false)
        }
    }

    private fun refreshInScope() {
        scope.launch { refresh() }
    }

    private fun cleanError(error: Throwable): String =
        error.message ?: error.toString().replaceFirst("Exception: ", "")
}

/** Pure logic from the PaymentAlerts widget. */
object PaymentAlertLogic {
    const val message: String = "Có thanh toán mới tại phòng khám"
    const val actionLabel: String = "Xem"
    const val financeTab: Int = 3

    fun shouldNotify(enabled: Boolean, session: Session, previous: FinanceState?, next: FinanceState): Boolean {
        if (!enabled) return false
        if (session.careMode || session.staffRole != "owner") return false
        if (previous?.data == null || next.data == null) return false
        return next.unread > previous.unread
    }
}
