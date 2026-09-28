package com.pema.clinic.feature.billing

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.shared.billing.Bill
import kotlin.test.Test

class BillingShotTest {
    @Test
    fun f11Cashier() {
        shotVsCanvas("F11") {
            BillingShot(Routes.Cashier, clinicState())
        }
    }

    @Test
    fun f12ConfirmPaymentSheet() {
        shotVsCanvas("F12") {
            BillingShot(Routes.Cashier, clinicState(), previewPaymentSheet = true)
        }
    }

    @Test
    fun g7PatientInvoicesReadOnly() {
        shotVsCanvas("G7") {
            BillingShot(
                route = Routes.Invoices,
                state = clinicState(showCollectAction = false, collectEnabled = false, showNewOrderAction = false),
            )
        }
    }

    @Composable
    private fun BillingShot(
        route: String,
        state: CashierUiState,
        previewPaymentSheet: Boolean = false,
    ) {
        CompositionLocalProvider(LocalOnBack provides {}) {
            CashierScreen(
                route = route,
                state = state,
                onConfirmPayment = {},
                onNewOrder = {},
                previewPaymentSheet = previewPaymentSheet,
            )
        }
    }

    private fun clinicState(
        showCollectAction: Boolean = true,
        collectEnabled: Boolean = true,
        showNewOrderAction: Boolean = true,
    ) = CashierUiState(
        patientId = "P001",
        patientName = "Nguyễn Thu Hà",
        bill = Bill(total = 580_000, paid = 0),
        invoiceLines = listOf(InvoiceLineUiState("DN-1", 580_000)),
        showCollectAction = showCollectAction,
        collectEnabled = collectEnabled,
        showNewOrderAction = showNewOrderAction,
    )
}
