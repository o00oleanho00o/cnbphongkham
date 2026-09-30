package com.pema.clinic.feature.aftercare

import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.patients.PatientState
import kotlin.test.Test

class AftercareShotTest {
    @Test
    fun g1HomeCare() {
        shotVsCanvas("G1") {
            DetailScaffold(title = Routes.titleOf(Routes.HomeCare), onBack = {}) {
                HomeCareScreen(
                    state = HomeCareUiState(acknowledged = false),
                    onAcknowledge = {},
                    onSendUpdate = {},
                )
            }
        }
    }

    @Test
    fun g2SendUpdatePhotoSelected() {
        val draft = SendUpdateDraft(
            initialText = "Da còn hơi đỏ ở má trái, không rát.",
            initialConsent = false,
            initialPhoto = sampleCapturedPhoto(),
        )
        shotVsCanvas("G2") {
            DetailScaffold(title = Routes.titleOf(Routes.SendUpdate), onBack = {}) {
                SendUpdateScreen(
                    draft = draft,
                    onCapture = {},
                    onRemovePhoto = {},
                    onSubmit = {},
                    photoPreview = PhotoPreviewMode.CanvasSummary,
                )
            }
        }
    }

    @Test
    fun g8PrivacyConsent() {
        shotVsCanvas("G8") {
            DetailScaffold(title = Routes.titleOf(Routes.Privacy), onBack = {}) {
                PrivacyScreen(consent = true, onConsentChange = {})
            }
        }
    }

    @Test
    fun f10FollowUpReply() {
        shotVsCanvas("F10") {
            DetailScaffold(title = Routes.titleOf(Routes.FollowUpReply), onBack = {}) {
                FollowUpReplyScreen(
                    profile = PatientProfile(
                        id = "P001",
                        name = "Nguyễn Thu Hà",
                        doctor = "BS. Tâm",
                        sessions = 2,
                        totalSessions = 6,
                        appointment = "10:30",
                        day = "2026-09-22",
                        careGroup = "",
                        caseLabel = "",
                    ),
                    patient = PatientState(
                        sessions = 2,
                        appointment = "10:30",
                        day = "2026-09-22",
                        escalations = listOf("Khách báo da đỏ nhẹ, cần bác sĩ xem ảnh."),
                        updates = listOf("Da hơi đỏ nhẹ vùng má sau một ngày, không ngứa."),
                    ),
                    reply = "",
                    onReplyChange = {},
                    onSubmit = {},
                )
            }
        }
    }
}
