package com.pema.clinic.feature.finance

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.PemaDialog
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.ProcedureService
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@Composable
internal fun RateScreen(
    state: FinanceState,
    onUpdateRate: suspend (service: String, rate: Int, basis: String) -> Boolean = { _, _, _ -> false },
) {
    var editing by remember { mutableStateOf<ProcedureService?>(null) }
    val snapshot = state.data
    FinanceDetailScaffold("Chính sách thủ thuật") {
        Text(
            "Thay đổi áp dụng cho lượt mới. Tỷ lệ lịch sử được giữ nguyên.",
            style = PemaType.body,
        )
        Spacer(ModifierHeight20)
        snapshot?.services.orEmpty().forEach { service ->
            MaterialRateCard(
                title = service.name,
                subtitle = "${service.ratePercent}% · ${service.basis} · phiên bản ${service.version}",
                onClick = { editing = service },
            )
        }
        if (state.error.isNotEmpty()) {
            Text(state.error, style = PemaType.of(14f, color = Color(0xFFFF5722)))
        }
    }
    editing?.let { service ->
        RateDialog(
            service = service,
            onDismiss = { editing = null },
            onSave = { rate, basis ->
                editing = null
                onUpdateRate(service.id, rate, basis)
            },
        )
    }
}

private val ModifierHeight20 = androidx.compose.ui.Modifier.height(20.dp)

@Composable
private fun RateDialog(
    service: ProcedureService,
    onDismiss: () -> Unit,
    onSave: suspend (Int, String) -> Boolean,
) {
    var rate by remember(service.id) { mutableStateOf(service.ratePercent.toString()) }
    var basis by remember(service.id) { mutableStateOf(service.basis) }
    val scope = rememberCoroutineScope()
    PemaDialog(
        title = service.name,
        onDismiss = onDismiss,
        confirmText = "Lưu",
        onConfirm = {
            val value = rate.toDoubleOrNull()
            if (value != null && value >= 0.0 && value <= 100.0) {
                scope.launch {
                    onSave((value * 100).roundToInt(), basis)
                }
            }
        },
        dismissText = "Hủy",
    ) {
        PemaTextField(
            value = rate,
            onValueChange = { rate = it },
            label = "Tỷ lệ %",
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        )
        Spacer(androidx.compose.ui.Modifier.height(12.dp))
        PemaDropdownField(
            value = basis,
            options = listOf("net", "list", "collected"),
            onSelected = { basis = it },
            display = {
                when (it) {
                    "net" -> "Giá sau giảm"
                    "list" -> "Giá niêm yết"
                    else -> "Theo thực thu"
                }
            },
        )
    }
}
