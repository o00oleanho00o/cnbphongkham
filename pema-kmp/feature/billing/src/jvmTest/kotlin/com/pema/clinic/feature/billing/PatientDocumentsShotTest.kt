package com.pema.clinic.feature.billing

import com.pema.clinic.core.ui.shots.shotVsCanvas
import kotlin.test.Test

class PatientDocumentsShotTest {
    @Test
    fun k2PatientDocuments() {
        shotVsCanvas("K2") {
            PatientDocumentsScreen(
                state = PatientDocumentsUiState(
                    invoices = listOf(
                        PatientDocumentTileUiState(
                            id = "HD-0001",
                            title = "Buổi chăm sóc / điều trị",
                            sub = "HD-0001 · 6/9/2026 · Đã thanh toán\n1.200.000 ₫",
                            icon = "receipt_long",
                        ),
                        PatientDocumentTileUiState(
                            id = "HD-DEMO-001",
                            title = "Tái khám & đánh giá",
                            sub = "HD-DEMO-001 · Đã thu một phần · còn 150.000 ₫",
                            icon = "receipt_long",
                        ),
                    ),
                    aftercare = listOf(
                        PatientDocumentTileUiState(
                            id = "aftercare",
                            title = "Hướng dẫn chăm sóc sau buổi",
                            sub = "Đã duyệt · 6/9/2026",
                            icon = "description",
                        ),
                    ),
                    prescriptions = listOf(
                        PatientDocumentTileUiState(
                            id = "DN-1",
                            title = "DN-1 · BS. Tâm",
                            sub = "Tretinoin 0.025% 20g · Kem chống nắng SPF50+",
                            icon = "medication",
                        ),
                    ),
                ),
                onOpenAftercare = {},
                onOpenPrescription = {},
                onBack = {},
            )
        }
    }
}
