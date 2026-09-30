package com.pema.clinic.feature.billing

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.shared.clinic.ClinicStore
import kotlin.test.Test

class InvoiceCashierShotTest {
    @Test
    fun i10CashierInvoices() {
        shotVsCanvas("I10") {
            InvoiceCashierShot(previewPaymentSheet = false)
        }
    }

    @Test
    fun i11PaymentMethodSheet() {
        shotVsCanvas("I11") {
            InvoiceCashierShot(previewPaymentSheet = true)
        }
    }

    @Composable
    private fun InvoiceCashierShot(previewPaymentSheet: Boolean) {
        CompositionLocalProvider(LocalOnBack provides {}) {
            InvoiceCashierScreen(
                state = buildInvoiceCashierState(ClinicStore().state.value, "all"),
                onFilterChange = {},
                onPay = { _, _, _, _ -> },
                previewPaymentSheet = previewPaymentSheet,
            )
        }
    }
}
