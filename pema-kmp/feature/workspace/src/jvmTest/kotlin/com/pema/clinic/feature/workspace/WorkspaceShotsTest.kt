package com.pema.clinic.feature.workspace

import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.shared.catalog.Catalog
import com.pema.clinic.shared.catalog.sampleCatalog
import com.pema.clinic.shared.finance.FinanceSnapshot
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.FinanceSummary
import com.pema.clinic.shared.finance.PaymentNotification
import com.pema.clinic.shared.patients.PatientState
import com.pema.clinic.shared.session.Session
import kotlin.test.Test

class WorkspaceShotsTest {
    private val catalog: Catalog = sampleCatalog()
    private val finance = FinanceState(
        month = "2026-09",
        data = FinanceSnapshot(
            month = "2026-09",
            today = "2026-09-22",
            periodStatus = "open",
            summary = FinanceSummary(revenue = 186_400_000, fee = 0, pending = 0, collected = 120_000_000, debt = 0),
            notifications = listOf(
                PaymentNotification("N1", "Có thanh toán mới", "Thanh toán mới tại phòng khám", read = false, at = "2026-09-22T10:00:00+07:00"),
            ),
        ),
    )

    private fun state(
        session: Session = Session(),
        tab: Int = 0,
        patient: PatientState? = null,
        reviewCount: Int = 0,
        showSheet: Boolean = false,
    ): WorkspaceUiState {
        val profile = catalog.profiles[session.selected.coerceIn(0, catalog.profiles.lastIndex)]
        val basePatient = patient ?: PatientState.fromProfile(profile)
        return WorkspaceUiState(
            session = session,
            catalog = catalog,
            profile = profile,
            patient = basePatient,
            selectedTab = tab,
            financeOn = true,
            financeState = finance,
            reviewProfiles = catalog.profiles.filter { session.owns(it) }.take(reviewCount),
            showAccountSheet = showSheet,
        )
    }

    @Test fun a1OwnerToday() {
        val profile = catalog.profiles[0]
        shotVsCanvas("A1") {
            WorkspaceScreen(
                state = state(
                    patient = PatientState.fromProfile(profile).copy(updates = listOf("Da hơi đỏ nhẹ vùng má sau một ngày, không ngứa.")),
                ),
            )
        }
    }

    @Test fun a2OwnerSchedule() {
        shotVsCanvas("A2") { WorkspaceScreen(state = state(tab = 1)) }
    }

    @Test fun a3OwnerPatientsFrame() {
        shotVsCanvas("A3") { WorkspaceScreen(state = state(tab = 2)) }
    }

    @Test fun a4OwnerReviewQueue() {
        val profile = catalog.profiles[0]
        shotVsCanvas("A4") {
            WorkspaceScreen(
                state = state(
                    tab = 3,
                    patient = PatientState.fromProfile(profile).copy(updates = listOf("Da hơi đỏ nhẹ vùng má sau một ngày, không ngứa.")),
                ),
            )
        }
    }

    @Test fun a5OwnerMore() {
        shotVsCanvas("A5") { WorkspaceScreen(state = state(tab = 4)) }
    }

    @Test fun a6AccountSheet() {
        val profile = catalog.profiles[0]
        shotVsCanvas("A6") {
            WorkspaceScreen(
                state = state(
                    patient = PatientState.fromProfile(profile).copy(updates = listOf("Da hơi đỏ nhẹ vùng má sau một ngày, không ngứa.")),
                    showSheet = true,
                ),
            )
        }
    }

    @Test fun b1DoctorWork() {
        shotVsCanvas("B1") {
            WorkspaceScreen(
                state = state(
                    session = Session(staffRole = "doctor", staffDoctor = "BS. Tâm", staffName = "BS. Tâm"),
                    reviewCount = 2,
                ),
            )
        }
    }

    @Test fun d1AccountantWork() {
        shotVsCanvas("D1") {
            WorkspaceScreen(state = state(session = Session(staffRole = "accountant", staffDoctor = "Kế toán", staffName = "Kế toán")))
        }
    }

    @Test fun e1CareHome() {
        val index = catalog.profiles.indexOfFirst { it.careGroup == "d1" }.coerceAtLeast(0)
        val session = Session(careMode = true, careSelected = index)
        val profile = catalog.profiles[index]
        shotVsCanvas("E1") { WorkspaceScreen(state = state(session = session, patient = PatientState.fromProfile(profile))) }
    }

    @Test fun e2CareJourney() {
        val index = catalog.profiles.indexOfFirst { it.careGroup == "d1" }.coerceAtLeast(0)
        shotVsCanvas("E2") { WorkspaceScreen(state = state(session = Session(careMode = true, careSelected = index), tab = 1)) }
    }

    @Test fun e3CareMessages() {
        val index = catalog.profiles.indexOfFirst { it.careGroup == "d1" }.coerceAtLeast(0)
        val profile = catalog.profiles[index]
        shotVsCanvas("E3") {
            WorkspaceScreen(
                state = state(
                    session = Session(careMode = true, careSelected = index),
                    tab = 2,
                    patient = PatientState.fromProfile(profile).copy(
                        updates = listOf("Da hơi đỏ nhẹ vùng má sau một ngày, không ngứa."),
                        response = "Đỏ nhẹ sau thủ thuật là bình thường. Tiếp tục dưỡng ẩm, tránh nắng và báo lại nếu rát tăng.",
                    ),
                ),
            )
        }
    }

    @Test fun e4CareProfile() {
        val index = catalog.profiles.indexOfFirst { it.careGroup == "d1" }.coerceAtLeast(0)
        shotVsCanvas("E4") { WorkspaceScreen(state = state(session = Session(careMode = true, careSelected = index), tab = 3)) }
    }

    @Test fun f16Guide() {
        shotVsCanvas("F16") { GuideScreen() }
    }
}
