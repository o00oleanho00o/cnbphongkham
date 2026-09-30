package com.pema.clinic.feature.billing

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredHeight
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.LazyDetailScaffold
import com.pema.clinic.core.ui.widgets.PemaBottomSheet
import com.pema.clinic.core.ui.widgets.PemaCardFilledButton
import com.pema.clinic.core.ui.widgets.PemaCardLine
import com.pema.clinic.core.ui.widgets.PemaCardTitle
import com.pema.clinic.core.ui.widgets.PemaChipWrap
import com.pema.clinic.core.ui.widgets.PemaEmpty
import com.pema.clinic.core.ui.widgets.PemaFilledButton
import com.pema.clinic.core.ui.widgets.PemaFilterChip
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaIcon
import com.pema.clinic.core.ui.widgets.PemaInfoCard
import com.pema.clinic.core.ui.widgets.PemaMetrics
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaText
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.clinic.ClinicError
import com.pema.clinic.shared.clinic.ClinicState
import com.pema.clinic.shared.clinic.money
import com.pema.clinic.shared.clinic.pay
import com.pema.clinic.shared.clinic.staffContext

private const val FilterAll = "all"
private const val FilterDue = "due"
private const val FilterPaid = "paid"
private val PaidGreen = Color(0xFF28745D)

fun NavGraphBuilder.invoiceCashierGraph(deps: FeatureDeps) {
    composable(Routes.CashierInvoices) { InvoiceCashierRoute(deps) }
}

@Composable
private fun InvoiceCashierRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val messenger = rememberPemaMessenger()
    var filter by rememberSaveable { mutableStateOf(FilterAll) }
    val state = remember(clinic, filter) { buildInvoiceCashierState(clinic, filter) }

    InvoiceCashierScreen(
        state = state,
        onFilterChange = { filter = it },
        onPay = { patientId, invoiceId, amount, method ->
            deps.clinicStore.pay(patientId, invoiceId, amount, method, session.staffContext())
            messenger.show("Đã ghi phiếu thu và cập nhật hóa đơn")
        },
    )
}

@Immutable
internal data class InvoiceCashierUiState(
    val filter: String,
    val totalInvoices: Int,
    val totalDueCompact: String,
    val collected: String,
    val invoices: List<InvoiceRowUiState>,
)

@Immutable
internal data class InvoiceRowUiState(
    val patientId: String,
    val invoiceId: String,
    val patientName: String,
    val date: String,
    val label: String,
    val amount: Int,
    val received: Int,
) {
    val due: Int get() = amount - received
    val paid: Boolean get() = received >= amount
}

internal fun buildInvoiceCashierState(state: ClinicState, filter: String): InvoiceCashierUiState {
    val all = state.patients.flatMap { patient ->
        patient.invoices.map { invoice ->
            InvoiceRowUiState(
                patientId = patient.id,
                invoiceId = invoice.id,
                patientName = patient.name,
                date = invoice.date,
                label = invoice.label,
                amount = invoice.amount,
                received = if (invoice.paid) invoice.amount else invoice.received,
            )
        }
    }
    val rows = all.filter {
        when (filter) {
            FilterDue -> it.received < it.amount
            FilterPaid -> it.received >= it.amount
            else -> true
        }
    }
    return InvoiceCashierUiState(
        filter = filter,
        totalInvoices = all.size,
        totalDueCompact = compactMillions(all.sumOf { it.due }),
        collected = money(all.sumOf { it.received }),
        invoices = rows,
    )
}

internal fun compactMillions(value: Int): String {
    if (value < 1_000_000) return money(value)
    val tenths = (value + 50_000) / 100_000
    val text = if (tenths % 10 == 0) (tenths / 10).toString() else "${tenths / 10},${tenths % 10}"
    return "${text}tr"
}

@Composable
internal fun InvoiceCashierScreen(
    state: InvoiceCashierUiState,
    onFilterChange: (String) -> Unit,
    onPay: (patientId: String, invoiceId: String, amount: Int, method: String) -> Unit,
    modifier: Modifier = Modifier,
    previewPaymentSheet: Boolean = false,
) {
    var selectedInvoice by remember { mutableStateOf<InvoiceRowUiState?>(null) }
    var method by remember { mutableStateOf("Tiền mặt") }
    var amount by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }

    fun openSheet(invoice: InvoiceRowUiState) {
        selectedInvoice = invoice
        method = "Tiền mặt"
        amount = invoice.due.toString()
        error = ""
    }

    fun submit(invoice: InvoiceRowUiState) {
        val value = amount.trim().toIntOrNull()
        if (value == null) {
            error = "Nhập số tiền hợp lệ."
            return
        }
        try {
            onPay(invoice.patientId, invoice.invoiceId, value, method)
            selectedInvoice = null
            error = ""
        } catch (e: ClinicError) {
            error = e.message.orEmpty()
        }
    }

    Box(modifier.fillMaxSize()) {
        LazyDetailScaffold(title = Routes.appBarTitleOf(Routes.CashierInvoices)) {
            item {
                PemaHeading("Thu ngân", "Hóa đơn & thanh toán · dữ liệu mẫu")
                PemaMetrics(
                    state.totalInvoices.toString() to "Tổng hóa đơn",
                    state.totalDueCompact to "Còn phải thu",
                )
                PemaTile(
                    "Đã thu lũy kế",
                    "${state.collected} · không thu trùng",
                    "account_balance_wallet",
                    onClick = null,
                )
                PemaChipWrap(Modifier.padding(bottom = 16.dp)) {
                    InvoiceFilterChip("Tất cả", FilterAll, state.filter, onFilterChange)
                    InvoiceFilterChip("Còn phải thu", FilterDue, state.filter, onFilterChange)
                    InvoiceFilterChip("Đã thanh toán", FilterPaid, state.filter, onFilterChange)
                }
            }
            if (state.invoices.isEmpty()) {
                item { PemaEmpty("Không có hóa đơn.") }
            } else {
                items(state.invoices.size, key = { state.invoices[it].patientId + state.invoices[it].invoiceId }) { index ->
                    InvoiceInfoCard(state.invoices[index], onPay = { openSheet(state.invoices[index]) })
                }
            }
        }

        if (previewPaymentSheet) {
            val invoice = selectedInvoice ?: state.invoices.firstOrNull { it.due > 0 }
            if (invoice != null) {
                StaticPaymentSheetOverlay(invoice = invoice, method = "Tiền mặt", onConfirm = {})
            }
        }
    }

    selectedInvoice?.let { invoice ->
        if (!previewPaymentSheet) {
            PemaBottomSheet(onDismiss = { selectedInvoice = null }) {
                PaymentMethodSheetBody(
                    invoice = invoice,
                    method = method,
                    onMethodChange = { method = it },
                    amount = amount,
                    onAmountChange = {
                        amount = it
                        error = ""
                    },
                    error = error,
                    onConfirm = { submit(invoice) },
                    showAmountField = true,
                )
            }
        }
    }
}

@Composable
private fun InvoiceFilterChip(label: String, value: String, selected: String, onFilterChange: (String) -> Unit) {
    PemaFilterChip(label, selected = selected == value, onClick = { onFilterChange(value) })
}

@Composable
private fun InvoiceInfoCard(row: InvoiceRowUiState, onPay: () -> Unit) {
    PemaInfoCard {
        PemaCardTitle(row.patientName)
        PemaText("${row.invoiceId} · ${row.date} · ${row.label}", size = 12f, color = PemaColors.Muted)
        Spacer(Modifier.height(4.dp))
        PemaCardLine("Tổng tiền", money(row.amount))
        PemaCardLine("Đã thu", money(row.received))
        PemaCardLine("Còn lại", money(row.due))
        if (row.due > 0) {
            Spacer(Modifier.height(8.dp))
            PemaCardFilledButton("Thu tiền", onClick = onPay)
        } else {
            PemaText("Đã thanh toán", size = 12f, color = PaidGreen, weight = FontWeight.W600)
        }
    }
}

@Composable
private fun PaymentMethodSheetBody(
    invoice: InvoiceRowUiState,
    method: String,
    onMethodChange: (String) -> Unit,
    amount: String,
    onAmountChange: (String) -> Unit,
    error: String,
    onConfirm: () -> Unit,
    modifier: Modifier = Modifier,
    showAmountField: Boolean,
) {
    Column(
        modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 16.dp),
        horizontalAlignment = Alignment.Start,
    ) {
        Text("Thu tiền · ${invoice.patientName}", style = PemaType.of(22f, FontWeight.W700, PemaColors.Ink, height = 1.3f))
        Text(
            "${invoice.invoiceId} · Còn lại ${money(invoice.due)}",
            style = PemaType.of(14f, color = PemaColors.Muted),
            modifier = Modifier.padding(top = 4.dp, bottom = 12.dp),
        )
        PaymentMethodRow("Tiền mặt", selected = method == "Tiền mặt", onClick = { onMethodChange("Tiền mặt") })
        PaymentMethodRow("Chuyển khoản", selected = method == "Chuyển khoản", onClick = { onMethodChange("Chuyển khoản") })
        if (showAmountField) {
            Spacer(Modifier.height(12.dp))
            PemaTextField(
                value = amount,
                onValueChange = onAmountChange,
                label = "Số tiền (VND)",
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            )
        }
        Spacer(Modifier.height(12.dp))
        PemaNotice("Số tiền mặc định bằng phần còn lại · không thu vượt dư nợ · không kết nối ngân hàng")
        if (error.isNotEmpty()) {
            Text(error, style = PemaType.of(14f, color = PemaColors.Error), modifier = Modifier.padding(bottom = 8.dp))
        }
        PemaFilledButton("Xác nhận thu tiền", onClick = onConfirm, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
private fun PaymentMethodRow(text: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 56.dp)
            .clip(RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        PemaIcon(
            if (selected) "radio_button_checked" else "radio_button_unchecked",
            size = 21.dp,
            color = if (selected) PemaColors.Blue else PemaColors.Muted,
        )
        Text(text, style = PemaType.of(16f, color = PemaColors.Ink))
    }
}

@Composable
private fun StaticPaymentSheetOverlay(invoice: InvoiceRowUiState, method: String, onConfirm: () -> Unit) {
    Box(
        Modifier
            .fillMaxWidth()
            .requiredHeight(844.dp)
            .offset(y = (-47).dp)
            .background(PemaColors.Black54),
    ) {
        Surface(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .offset(y = 24.dp)
                .fillMaxWidth()
                .height(451.dp),
            shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp),
            color = PemaColors.White,
            tonalElevation = 0.dp,
        ) {
            Column(Modifier.fillMaxWidth()) {
                Box(Modifier.fillMaxWidth().height(48.dp), contentAlignment = Alignment.Center) {
                    Box(
                        Modifier
                            .size(width = 32.dp, height = 4.dp)
                            .background(PemaColors.OnSurfaceVariant.copy(alpha = 0.4f), RoundedCornerShape(2.dp)),
                    )
                }
                PaymentMethodSheetBody(
                    invoice = invoice,
                    method = method,
                    onMethodChange = {},
                    amount = invoice.due.toString(),
                    onAmountChange = {},
                    error = "",
                    onConfirm = onConfirm,
                    showAmountField = false,
                )
                Spacer(Modifier.height(34.dp))
            }
        }
    }
}
