package com.pema.clinic.feature.orders

import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.shared.catalog.Product
import com.pema.clinic.shared.orders.Order
import com.pema.clinic.shared.patients.CartLine
import kotlin.test.Test

class OrdersShotTest {
    @Test
    fun f4QuickOrder() {
        shotVsCanvas("F4") {
            QuickOrderScreen(
                state = QuickOrderUiState(
                    patientId = "P001",
                    patientName = "Nguyễn Thu Hà",
                    catalogCount = 115,
                    cartCount = 2,
                    cartTotal = 720_000,
                    products = shotProducts,
                ),
                filter = "",
                onFilterChange = {},
                onOpenReview = {},
                onAddProduct = {},
                onBack = {},
            )
        }
    }

    @Test
    fun f5OrderReview() {
        shotVsCanvas("F5") {
            OrderReviewScreen(
                state = OrderReviewUiState(
                    patientId = "P001",
                    lines = listOf(
                        CartLine(product = shotProducts[1], route = "CONSULTATION", usage = "Thoa mỏng 2 lần/ngày sau làm sạch"),
                        CartLine(product = shotProducts[5], route = "UNRESOLVED", usage = ""),
                    ),
                    cartTotal = 720_000,
                    cartReady = false,
                ),
                onDecrease = {},
                onIncrease = {},
                onRemove = {},
                onRouteChange = { _, _ -> },
                onUsageChange = { _, _ -> },
                onSaveDraft = {},
                onApprove = {},
                onBack = {},
            )
        }
    }

    @Test
    fun f6ClinicPrescriptions() {
        shotVsCanvas("F6") {
            PrescriptionsScreen(
                state = shotPrescriptionsState(careMode = false),
                onEdit = {},
                onOpenA5 = {},
                onBack = {},
            )
        }
    }

    @Test
    fun f7A5PrintPreview() {
        shotVsCanvas("F7") {
            A5PrintPreviewScreen(
                state = A5PrintUiState(
                    patientName = "Nguyễn Thu Hà",
                    orders = listOf(approvedShotOrder),
                ),
                onBack = {},
            )
        }
    }

    @Test
    fun g6CarePrescriptions() {
        shotVsCanvas("G6") {
            PrescriptionsScreen(
                state = shotPrescriptionsState(careMode = true),
                onEdit = {},
                onOpenA5 = {},
                onBack = {},
            )
        }
    }
}

private val shotProducts = listOf(
    Product("TH021", "TH021", "Doxycycline 100mg", "Viên", "Thuốc", 4_500, "PRESCRIPTION"),
    Product("SP014", "SP014", "Kem dưỡng phục hồi B5 40ml", "Tuýp", "Dược mỹ phẩm", 320_000, "CONSULTATION"),
    Product("SP032", "SP032", "Sữa rửa mặt dịu nhẹ 200ml", "Chai", "Dược mỹ phẩm", 285_000, "CONSULTATION"),
    Product("SP047", "SP047", "Kem chống nắng SPF50+ 50ml", "Tuýp", "Dược mỹ phẩm", 435_000, "CONSULTATION"),
    Product("TH008", "TH008", "Tretinoin 0.025% 20g", "Tuýp", "Thuốc", 145_000, "PRESCRIPTION"),
    Product("SP060", "SP060", "Serum phục hồi HA 30ml", "Chai", "Dược mỹ phẩm", 400_000, "UNRESOLVED"),
)

private val approvedShotOrder = Order(
    id = "DN-1",
    patientId = "P001",
    patientName = "Nguyễn Thu Hà",
    approved = true,
    items = listOf(
        CartLine(
            product = shotProducts[4],
            route = "PRESCRIPTION",
            usage = "Thoa mỏng buổi tối, tránh vùng mắt",
        ),
        CartLine(
            product = shotProducts[3],
            route = "CONSULTATION",
            usage = "Thoa mỗi sáng, thoa lại sau 2–3 giờ",
        ),
    ),
)

private fun shotPrescriptionsState(careMode: Boolean) = PrescriptionsUiState(
    patientId = "P001",
    patientName = "Nguyễn Thu Hà",
    careMode = careMode,
    orders = listOf(approvedShotOrder),
    title = Routes.titleOf(Routes.Prescriptions),
)
