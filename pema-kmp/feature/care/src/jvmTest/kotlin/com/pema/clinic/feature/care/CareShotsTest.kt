package com.pema.clinic.feature.care

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.widgets.PemaBottomNav
import com.pema.clinic.core.ui.widgets.PemaMainTopBar
import com.pema.clinic.core.ui.widgets.PemaNavItem
import com.pema.clinic.core.ui.widgets.PemaScaffold
import com.pema.clinic.shared.care.CareCase
import com.pema.clinic.shared.care.CareQueueFilter
import com.pema.clinic.shared.care.careNotContacted
import com.pema.clinic.shared.catalog.sampleCatalog
import com.pema.clinic.shared.patients.PatientState
import kotlin.test.Test

class CareShotsTest {
    private val profiles = sampleCatalog().profiles.filter { it.inCareQueue }

    @Test
    fun c1Queue() {
        shotVsCanvas("C1") {
            CareWorkspaceFrame {
                CareQueueContent(
                    cases = profiles.map { CareCase(it) },
                    staffName = "Mai Anh",
                    filter = CareQueueFilter(),
                    searchText = "",
                    onBucketChange = {},
                    onSearchChange = {},
                    onFilterClick = {},
                    onClearGroup = {},
                    onOpenProfile = {},
                )
            }
        }
    }

    @Test
    fun c2GroupSheet() {
        val cases = profiles.map { CareCase(it) }
        shotVsCanvas("C2") {
            Box(Modifier.fillMaxSize()) {
                CareWorkspaceFrame {
                    CareQueueContent(
                        cases = cases,
                        staffName = "Mai Anh",
                        filter = CareQueueFilter(),
                        searchText = "",
                        onBucketChange = {},
                        onSearchChange = {},
                        onFilterClick = {},
                        onClearGroup = {},
                        onOpenProfile = {},
                    )
                }
                CareGroupSheetOverlay(cases = cases, selectedGroup = "all")
            }
        }
    }

    @Test
    fun c3ActiveFilter() {
        shotVsCanvas("C3") {
            CareWorkspaceFrame {
                CareQueueContent(
                    cases = profiles.map { CareCase(it) },
                    staffName = "Mai Anh",
                    filter = CareQueueFilter(group = "overdue", bucket = careNotContacted),
                    searchText = "",
                    onBucketChange = {},
                    onSearchChange = {},
                    onFilterClick = {},
                    onClearGroup = {},
                    onOpenProfile = {},
                )
            }
        }
    }

    @Test
    fun c4EmptyFilter() {
        val cases = profiles.map { CareCase(it) }
        shotVsCanvas("C4") {
            CareWorkspaceFrame {
                CareQueueContent(
                    cases = cases,
                    staffName = "Mai Anh",
                    filter = CareQueueFilter(group = "d7", bucket = "Đã liên hệ"),
                    searchText = "",
                    onBucketChange = {},
                    onSearchChange = {},
                    onFilterClick = {},
                    onClearGroup = {},
                    onOpenProfile = {},
                )
            }
        }
    }

    @Test
    fun c6ContactScreen() {
        val profile = profiles.first { it.careGroup == "d3" }
        val patient = PatientState.fromProfile(profile).copy(careNote = "Đã gọi, khách hẹn gửi ảnh tiến triển tối nay.")
        shotVsCanvas("C6") {
            CustomerCareContactContent(
                profile = profile,
                patient = patient,
                text = "",
                onTextChange = {},
                onSave = {},
                onRebook = {},
                onHandOff = {},
                onBack = {},
            )
        }
    }
}

@Composable
private fun CareWorkspaceFrame(content: @Composable () -> Unit) {
    PemaScaffold(
        topBar = { PemaMainTopBar("CSKH", onRoleClick = {}, unread = null) },
        bottomBar = {
            PemaBottomNav(
                listOf(
                    PemaNavItem("Công việc", "work"),
                    PemaNavItem("Hồ sơ mẫu", "people_outline", "people"),
                ),
                selectedIndex = 0,
                onSelect = {},
            )
        },
    ) { inner: PaddingValues ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(inner)
                .verticalScroll(rememberScrollState())
                .padding(start = 20.dp, top = 8.dp, end = 20.dp, bottom = 24.dp),
        ) {
            content()
        }
    }
}

@Composable
private fun CareGroupSheetOverlay(cases: List<CareCase>, selectedGroup: String) {
    Box(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxWidth().height(844.dp).offset(y = (-47).dp).background(PemaColors.Black54))
        Column(
            Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .heightIn(max = 720.dp)
                .background(PemaColors.White, RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp)),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(Modifier.fillMaxWidth().height(48.dp), contentAlignment = Alignment.Center) {
                Box(Modifier.fillMaxWidth(0.082f).height(4.dp).background(PemaColors.OnSurfaceVariant.copy(alpha = 0.4f), RoundedCornerShape(2.dp)))
            }
            Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                CareGroupSheetContent(cases = cases, selectedGroup = selectedGroup, onSelect = {})
            }
            Spacer(Modifier.height(34.dp))
        }
    }
}
