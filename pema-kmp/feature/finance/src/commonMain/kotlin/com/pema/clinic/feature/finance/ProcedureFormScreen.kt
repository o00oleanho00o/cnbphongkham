package com.pema.clinic.feature.finance

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.PemaDialog
import com.pema.clinic.core.ui.widgets.PemaFilledButton
import com.pema.clinic.core.ui.widgets.PemaTextButton
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.ProcedureEntry
import com.pema.clinic.shared.finance.ProcedureShare
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@Immutable
internal data class ProcedureFormValues(
    val patient: String,
    val invoice: String,
    val service: String,
    val date: String,
    val gross: String,
    val discount: String,
    val doctor: String,
    val assistant: String,
    val share: String,
    val rate: String,
    val rate2: String,
    val note: String,
)

internal fun buildProcedureEntry(values: ProcedureFormValues): ProcedureEntry {
    val mainShare = (values.share.toDouble() * 100).roundToInt()
    return ProcedureEntry(
        patient = values.patient,
        invoice = values.invoice,
        service = values.service,
        date = values.date,
        listPrice = values.gross.toIntOrNull() ?: -1,
        discount = values.discount.toIntOrNull() ?: -1,
        note = values.note,
        people = buildList {
            add(
                ProcedureShare(
                    doctor = values.doctor,
                    share = mainShare,
                    rate = (values.rate.toDouble() * 100).roundToInt(),
                ),
            )
            if (values.assistant.isNotEmpty()) {
                add(
                    ProcedureShare(
                        doctor = values.assistant,
                        share = 10_000 - mainShare,
                        rate = (values.rate2.toDouble() * 100).roundToInt(),
                    ),
                )
            }
        },
    )
}

internal fun validateProcedureForm(values: ProcedureFormValues): String? {
    val required = listOf(
        values.patient,
        values.service,
        values.date,
        values.gross,
        values.discount,
        values.doctor,
        values.share,
        values.rate,
        values.note,
    ) + if (values.assistant.isNotEmpty()) listOf(values.rate2) else emptyList()
    if (required.any { it.trim().isEmpty() }) return "Cần nhập trường này"
    val numbers = listOf(values.gross, values.discount, values.share, values.rate) +
        if (values.assistant.isNotEmpty()) listOf(values.rate2) else emptyList()
    if (numbers.any { it.toDoubleOrNull()?.isFinite() != true }) return "Nhập số hợp lệ"
    return null
}

@Composable
internal fun ProcedureFormScreen(
    state: FinanceState,
    initialPatient: String = "P001",
    patientIds: List<String>? = null,
    onSubmit: suspend (ProcedureEntry) -> Boolean = { false },
    onDone: () -> Unit = {},
) {
    val snapshot = state.data
    if (snapshot == null) {
        FinanceDetailScaffold("Ghi lượt đã thực hiện") {
            Text("Đang tải dữ liệu tài chính...", style = PemaType.body)
        }
        return
    }
    val firstService = snapshot.services.firstOrNull()
    var patient by remember(initialPatient) { mutableStateOf(initialPatient) }
    var service by remember(firstService?.id) { mutableStateOf(firstService?.id.orEmpty()) }
    var day by remember(snapshot.today) { mutableStateOf(snapshot.today) }
    var gross by remember(firstService?.id) { mutableStateOf(firstService?.price?.toString().orEmpty()) }
    var discount by remember { mutableStateOf("0") }
    var invoice by remember { mutableStateOf("") }
    var doctor by remember(snapshot.doctors) { mutableStateOf(snapshot.doctors.firstOrNull()?.id.orEmpty()) }
    var share by remember { mutableStateOf("100") }
    var rate by remember(firstService?.id) { mutableStateOf(firstService?.ratePercent?.toString().orEmpty()) }
    var assistant by remember { mutableStateOf("") }
    var rate2 by remember { mutableStateOf("0") }
    var note by remember { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }
    var localError by remember { mutableStateOf("") }
    var dayDialog by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun values() = ProcedureFormValues(
        patient = patient,
        invoice = invoice,
        service = service,
        date = day,
        gross = gross,
        discount = discount,
        doctor = doctor,
        assistant = assistant,
        share = share,
        rate = rate,
        rate2 = rate2,
        note = note,
    )

    FinanceDetailScaffold("Ghi lượt đã thực hiện") {
        PemaDropdownField(
            value = patient,
            options = ((patientIds ?: List(36) { "P${(it + 1).toString().padStart(3, '0')}" }) + initialPatient).distinct(),
            onSelected = { patient = it },
            label = "Hồ sơ",
        )
        Spacer(Modifier.height(14.dp))
        PemaDropdownField(
            value = service,
            options = snapshot.services.map { it.id },
            onSelected = { selected ->
                service = selected
                val next = snapshot.services.first { it.id == selected }
                gross = next.price.toString()
                rate = next.ratePercent.toString()
            },
            label = "Thủ thuật",
            display = { id -> snapshot.services.firstOrNull { it.id == id }?.name ?: id },
        )
        Spacer(Modifier.height(14.dp))
        PemaTextButton(
            text = "Ngày thực hiện $day",
            onClick = { dayDialog = true },
            icon = "calendar_month",
            iconFilled = true,
            modifier = Modifier.align(Alignment.CenterHorizontally),
        )
        ProcedureField("Giá niêm yết (VND)", gross, { gross = it })
        ProcedureField("Giảm giá (VND)", discount, { discount = it })
        PemaDropdownField(
            value = invoice,
            options = listOf("") + snapshot.invoices.map { it.id },
            onSelected = { invoice = it },
            label = "Gắn hóa đơn đã có",
            display = { id ->
                if (id.isEmpty()) {
                    "Tạo hóa đơn mới cho lượt này"
                } else {
                    snapshot.invoices.firstOrNull { it.id == id }?.let { "${it.patient} · ${it.id}" } ?: id
                }
            },
        )
        Spacer(Modifier.height(14.dp))
        PemaDropdownField(
            value = doctor,
            options = snapshot.doctors.map { it.id },
            onSelected = { doctor = it },
            label = "Bác sĩ chính",
            display = { id -> snapshot.doctors.firstOrNull { it.id == id }?.name ?: id },
        )
        Spacer(Modifier.height(14.dp))
        ProcedureField("Tỷ trọng doanh số bác sĩ chính %", share, { share = it })
        ProcedureField("Tỷ lệ tiền bác sĩ chính %", rate, { rate = it })
        PemaDropdownField(
            value = assistant,
            options = listOf("") + snapshot.doctors.map { it.id },
            onSelected = { assistant = it },
            label = "Người phối hợp",
            display = { id -> if (id.isEmpty()) "Không có" else snapshot.doctors.firstOrNull { it.id == id }?.name ?: id },
        )
        Spacer(Modifier.height(14.dp))
        if (assistant.isNotEmpty()) {
            ProcedureField("Tỷ lệ tiền người phối hợp %", rate2, { rate2 = it })
        }
        Text(
            "Người phối hợp nhận phần tỷ trọng doanh số còn lại. Tổng tỷ lệ tiền không quá 100%.",
            style = PemaType.of(12f, color = PemaColors.Ink),
        )
        Spacer(Modifier.height(12.dp))
        PemaTextField(
            value = note,
            onValueChange = { note = it },
            label = "Ghi chú xác nhận hoàn tất",
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
        )
        Spacer(Modifier.height(14.dp))
        val error = localError.ifEmpty { state.error }
        if (error.isNotEmpty()) {
            Text(error, style = PemaType.of(14f, color = Color(0xFFFF5722)))
            Spacer(Modifier.height(8.dp))
        }
        PemaFilledButton(
            text = "Ghi nhận • Chờ kế toán duyệt",
            onClick = {
                val current = values()
                val validation = validateProcedureForm(current)
                if (validation != null) {
                    localError = validation
                    return@PemaFilledButton
                }
                scope.launch {
                    saving = true
                    val ok = onSubmit(buildProcedureEntry(current))
                    saving = false
                    if (ok) onDone()
                }
            },
            enabled = !saving,
            modifier = Modifier.fillMaxWidth(),
        )
    }
    if (dayDialog) {
        var input by remember(day) { mutableStateOf(day) }
        PemaDialog(
            title = "Ngày thực hiện",
            onDismiss = { dayDialog = false },
            confirmText = "Xác nhận",
            onConfirm = {
                if (input.trim().isNotEmpty()) {
                    day = input.trim()
                    dayDialog = false
                }
            },
            dismissText = "Quay lại",
        ) {
            PemaTextField(input, { input = it })
        }
    }
}

@Composable
private fun ProcedureField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    number: Boolean = true,
) {
    PemaTextField(
        value = value,
        onValueChange = onValueChange,
        label = label,
        keyboardOptions = KeyboardOptions(keyboardType = if (number) KeyboardType.Number else KeyboardType.Text),
    )
    Spacer(Modifier.height(14.dp))
}
