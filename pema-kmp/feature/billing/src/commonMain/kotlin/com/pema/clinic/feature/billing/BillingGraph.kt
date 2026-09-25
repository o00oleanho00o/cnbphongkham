package com.pema.clinic.feature.billing

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredHeight
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.moneyFormat
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.PemaBottomSheet
import com.pema.clinic.core.ui.widgets.PemaFilledButton
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaHero
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.billing.Bill
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.orders.Order
import com.pema.clinic.shared.session.Session

fun NavGraphBuilder.billingGraph(deps: FeatureDeps) {
    composable(Routes.Invoices) { CashierRoute(Routes.Invoices, deps) }
    composable(Routes.Cashier) { CashierRoute(Routes.Cashier, deps) }
}

@Composable
private fun CashierRoute(route: String, deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val allOrders by deps.ordersStore.state.collectAsStateWithLifecycle()
    val receipts by deps.receiptsStore.state.collectAsStateWithLifecycle()
    val profile = deps.catalogRepository.catalog().profiles[session.selected]
    val patientOrders = allOrders.filter { it.patientId == profile.id }
    val state = buildCashierState(
        session = session,
        profile = profile,
        orders = patientOrders,
        paid = receipts[profile.id] ?: 0,
    )

    CashierScreen(
        route = route,
        state = state,
        onConfirmPayment = { deps.receiptsStore.settle(state.patientId, state.bill.total) },
        onNewOrder = { deps.navigator.go(Routes.QuickOrder) },
    )
}

@Immutable
internal data class InvoiceLineUiState(
    val id: String,
    val total: Int,
)

@Immutable
internal data class CashierUiState(
    val patientId: String,
    val patientName: String,
    val bill: Bill,
    val invoiceLines: List<InvoiceLineUiState>,
    val showCollectAction: Boolean,
    val collectEnabled: Boolean,
    val showNewOrderAction: Boolean,
)

internal fun buildCashierState(
    session: Session,
    profile: PatientProfile,
    orders: List<Order>,
    paid: Int,
): CashierUiState {
    val bill = Bill(total = orders.sumOf { it.total }, paid = paid)
    val canCollect = !session.careMode && session.billing
    return CashierUiState(
        patientId = profile.id,
        patientName = profile.name,
        bill = bill,
        invoiceLines = orders.map { InvoiceLineUiState(id = it.id, total = it.total) },
        showCollectAction = canCollect,
        collectEnabled = canCollect && !bill.settled,
        showNewOrderAction = !session.careMode && session.clinical,
    )
}

@Composable
internal fun CashierScreen(
    route: String,
    state: CashierUiState,
    onConfirmPayment: () -> Unit,
    onNewOrder: () -> Unit,
    modifier: Modifier = Modifier,
    previewPaymentSheet: Boolean = false,
) {
    var showPaymentSheet by remember { mutableStateOf(false) }

    Box(modifier.fillMaxSize()) {
        DetailScaffold(title = Routes.titleOf(route)) {
            PemaHeading("Khoản cần thanh toán", state.patientName)
            PemaHero(
                moneyFormat(state.bill.due),
                "Đã thu ${moneyFormat(state.bill.paid)}",
                "payments",
            )
            state.invoiceLines.forEach { line ->
                PemaTile(line.id, moneyFormat(line.total), "receipt_long", onClick = null)
            }
            if (state.showCollectAction) {
                PemaPrimary(
                    "Thu đủ phần còn lại",
                    onClick = if (state.collectEnabled) ({ showPaymentSheet = true }) else null,
                )
            }
            if (state.showNewOrderAction) {
                PemaPrimary("Lên đơn mới", onClick = onNewOrder)
            }
        }

        if (previewPaymentSheet) {
            PaymentSheetPreviewOverlay(
                due = state.bill.due,
                onConfirmPayment = onConfirmPayment,
            )
        }
    }

    if (showPaymentSheet && !previewPaymentSheet) {
        PemaBottomSheet(onDismiss = { showPaymentSheet = false }) {
            PaymentSheetBody(
                due = state.bill.due,
                onConfirmPayment = {
                    onConfirmPayment()
                    showPaymentSheet = false
                },
            )
        }
    }
}

@Composable
internal fun PaymentSheetBody(
    due: Int,
    onConfirmPayment: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier.fillMaxWidth().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Xác nhận thu tiền", style = PemaType.heading)
            Text(moneyFormat(due), style = PemaType.sub13)
        }
        Spacer(Modifier.height(20.dp))
        Text(
            "Giao dịch mẫu · Không kết nối ngân hàng",
            style = PemaType.notice,
            modifier = Modifier
                .padding(bottom = 16.dp)
                .background(PemaColors.Tint, RoundedCornerShape(14.dp))
                .padding(16.dp),
        )
        PemaFilledButton(
            "Xác nhận tiền mặt",
            onClick = onConfirmPayment,
            modifier = Modifier.padding(vertical = 8.dp),
        )
    }
}

@Composable
private fun PaymentSheetPreviewOverlay(
    due: Int,
    onConfirmPayment: () -> Unit,
) {
    // The JVM shot harness renders feature content below the 47dp canvas status bar.
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
                .height(342.dp),
            shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp),
            color = PemaColors.White,
            tonalElevation = 0.dp,
        ) {
            Column(Modifier.fillMaxWidth()) {
                PaymentSheetHandle()
                PaymentSheetBody(due = due, onConfirmPayment = onConfirmPayment)
                Spacer(Modifier.height(34.dp))
            }
        }
    }
}

@Composable
private fun PaymentSheetHandle() {
    Box(
        Modifier.fillMaxWidth().height(48.dp),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier
                .size(width = 32.dp, height = 4.dp)
                .background(PemaColors.OnSurfaceVariant.copy(alpha = 0.4f), RoundedCornerShape(2.dp)),
        )
    }
}
