package com.pema.clinic.feature.finance

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.LocalPemaSnackbar
import com.pema.clinic.core.ui.widgets.PemaAction
import com.pema.clinic.core.ui.widgets.PemaActions
import com.pema.clinic.core.ui.widgets.PemaBottomNav
import com.pema.clinic.core.ui.widgets.PemaDialog
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaHero
import com.pema.clinic.core.ui.widgets.PemaMainTopBar
import com.pema.clinic.core.ui.widgets.PemaMetrics
import com.pema.clinic.core.ui.widgets.PemaNavItem
import com.pema.clinic.core.ui.widgets.PemaScaffold
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.shared.finance.FinanceDoctor
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.PaymentNotification
import com.pema.clinic.shared.finance.ProcedureRow
import kotlin.test.Test

class FinanceShotsTest {
    @Test fun h1OwnerOverview() {
        shotVsCanvas("H1") {
            FinanceScreen(state = FinanceState(month = "2026-09", data = ownerOverviewFixture()), initialTab = 0, lockRole = true)
        }
    }

    @Test fun h2DoctorOverview() {
        shotVsCanvas("H2") {
            FinanceScreen(
                state = FinanceState(month = "2026-09", role = "doctor", doctor = "D0", data = financeFixture(role = "doctor")),
                initialTab = 0,
                lockRole = true,
            )
        }
    }

    @Test fun h3Procedures() {
        shotVsCanvas("H3") {
            FinanceScreen(state = FinanceState(month = "2026-09", data = financeFixture(payments = 1)), initialTab = 1, lockRole = true)
        }
    }

    @Test fun h4ClosePeriodDialog() {
        shotVsCanvas("H4") {
            Box {
                FinanceScreen(state = FinanceState(month = "2026-09", data = financeFixture(payments = 1)), initialTab = 1, lockRole = true)
                PemaDialog(
                    title = "Gõ CHOT để khóa kỳ 2026-09",
                    onDismiss = {},
                    confirmText = "Xác nhận",
                    onConfirm = {},
                    dismissText = "Quay lại",
                ) {
                    PemaTextField("CHOT", {})
                }
            }
        }
    }

    @Test fun h5Payments() {
        shotVsCanvas("H5") {
            FinanceScreen(state = FinanceState(month = "2026-09", data = financeFixture(payments = 1)), initialTab = 2, lockRole = true)
        }
    }

    @Test fun h6Notifications() {
        shotVsCanvas("H6") {
            FinanceScreen(state = FinanceState(month = "2026-09", data = notificationsFixture()), initialTab = 3, lockRole = true)
        }
    }

    @Test fun h7Error() {
        shotVsCanvas("H7") {
            FinanceScreen(
                state = FinanceState(
                    month = "2026-09",
                    error = "Chưa kết nối dữ liệu tài chính. Kiểm tra dịch vụ và thử lại.",
                ),
                initialTab = 0,
                lockRole = true,
            )
        }
    }

    @Test fun h8Rates() {
        shotVsCanvas("H8") {
            RateScreen(state = FinanceState(month = "2026-09", data = financeFixture(payments = 0)))
        }
    }

    @Test fun h9ProcedureForm() {
        shotVsCanvas("H9") {
            ProcedureFormScreen(
                state = FinanceState(month = "2026-09", data = financeFixture(payments = 0)),
                initialPatient = "P001",
                patientIds = listOf("P001", "P002", "P003", "P004", "P005"),
            )
        }
    }

    @Test fun a7PaymentSnackbar() {
        shotVsCanvas("A7") {
            PaymentSnackbarPreview()
        }
    }
}

private fun ownerOverviewFixture() = financeFixture(payments = 1).copy(
    rows = listOf(
        ProcedureRow("D0-SUM", "2026-09-01", "P001", "Tổng hợp", "D0", "approved", 84_200_000, 1_000, 84_200_000, 8_420_000),
        ProcedureRow("D1-SUM", "2026-09-01", "P002", "Tổng hợp", "D1", "approved", 51_600_000, 1_000, 51_600_000, 5_160_000),
        ProcedureRow("D2-SUM", "2026-09-01", "P003", "Tổng hợp", "D2", "approved", 32_100_000, 1_000, 32_100_000, 3_210_000),
        ProcedureRow("D3-SUM", "2026-09-01", "P004", "Tổng hợp", "D3", "approved", 18_500_000, 1_000, 18_500_000, 1_850_000),
    ),
)

private fun notificationsFixture() = financeFixture(payments = 0).copy(
    notifications = listOf(
        PaymentNotification(
            id = "PT-1",
            title = "Đã thu 1.200.000 ₫",
            body = "Kế toán thu tiền mặt · P005 · HD-2609-011",
            read = false,
            at = "2026-09-22T09:41:00+07:00",
        ),
        PaymentNotification(
            id = "PT-2",
            title = "Đã thu 300.000 ₫",
            body = "Kế toán thu tiền mặt · P011 · HD-2609-009",
            read = true,
            at = "2026-09-21T16:05:00+07:00",
        ),
    ),
)

@Composable
private fun PaymentSnackbarPreview() {
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(snackbar) {
        snackbar.showSnackbar(message = "Có thanh toán mới tại phòng khám", actionLabel = "Xem")
    }
    CompositionLocalProvider(LocalPemaSnackbar provides snackbar) {
        PemaScaffold(
            topBar = { PemaMainTopBar("Clinic", onRoleClick = {}, unread = 1) },
            bottomBar = {
                PemaBottomNav(
                    items = listOf(
                        PemaNavItem("Hôm nay", "space_dashboard"),
                        PemaNavItem("Lịch hẹn", "calendar_month"),
                        PemaNavItem("Hồ sơ", "people_outline", "people"),
                        PemaNavItem("Theo dõi", "inbox"),
                        PemaNavItem("Thêm", "grid_view"),
                    ),
                    selectedIndex = 0,
                    onSelect = {},
                )
            },
        ) { inner ->
            Column(
                Modifier
                    .fillMaxSize()
                    .padding(inner)
                    .verticalScroll(rememberScrollState())
                    .padding(start = 20.dp, top = 8.dp, end = 20.dp, bottom = 24.dp),
            ) {
                PemaHeading("Chào buổi sáng, BS. Tâm", "Thứ Ba · 22 tháng 09, 2026")
                PemaHero("Một ngày chăm sóc\ntrọn vẹn hơn.", "1 phản hồi cần theo dõi", "wb_sunny")
                Spacer(Modifier.height(16.dp))
                PemaMetrics("12" to "Lịch hôm nay", "03" to "Đang chờ")
                PemaTile("Tài chính phòng khám", "Tháng 2026-09 · 186.400.000 ₫", "account_balance_wallet", onClick = {})
                PemaSection("Bắt đầu nhanh")
                PemaActions(
                    listOf(
                        PemaAction("Lên đơn", "note_add") {},
                        PemaAction("Đặt lịch", "calendar_month") {},
                        PemaAction("Thu ngân", "payments") {},
                    ),
                )
            }
        }
    }
}
