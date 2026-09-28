package com.pema.clinic.core.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.shots.shotVsCanvas
import com.pema.clinic.core.ui.widgets.PemaAction
import com.pema.clinic.core.ui.widgets.PemaActions
import com.pema.clinic.core.ui.widgets.PemaBottomNav
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaHero
import com.pema.clinic.core.ui.widgets.PemaMainTopBar
import com.pema.clinic.core.ui.widgets.PemaMetrics
import com.pema.clinic.core.ui.widgets.PemaNavItem
import com.pema.clinic.core.ui.widgets.PemaScaffold
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaSearchField
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaFilterChip
import com.pema.clinic.core.ui.widgets.PemaChipWrap
import com.pema.clinic.core.ui.widgets.PemaCheckRow
import com.pema.clinic.core.ui.widgets.PemaOutlinedButton
import com.pema.clinic.core.ui.widgets.PemaTextButton
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.WeekStrip
import kotlin.test.Test

/** Renders block compositions of canvas screens to build/shots and compares them with the refs. */
class BlocksShotTest {
    private val ownerNav = listOf(
        PemaNavItem("Hôm nay", "space_dashboard"),
        PemaNavItem("Lịch hẹn", "calendar_month"),
        PemaNavItem("Hồ sơ", "people_outline", "people"),
        PemaNavItem("Theo dõi", "inbox"),
        PemaNavItem("Thêm", "grid_view"),
    )

    @Test
    fun a1OwnerHome() {
        shotVsCanvas("A1") {
            PemaScaffold(
                topBar = { PemaMainTopBar("Clinic", onRoleClick = {}, unread = 1) },
                bottomBar = { PemaBottomNav(ownerNav, 0, {}) },
            ) { inner ->
                Column(Modifier.fillMaxSize().padding(inner).verticalScroll(rememberScrollState()).padding(start = 20.dp, top = 8.dp, end = 20.dp, bottom = 24.dp)) {
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
                    PemaSection("Lượt khám tiếp theo")
                    PemaTile("Nguyễn Thu Hà", "10:30 · Chờ tiếp nhận · Tái khám", "person", onClick = {})
                    PemaTile("Theo dõi sau điều trị", "Xem ảnh và phản hồi từ người bệnh", "inbox", onClick = {})
                }
            }
        }
    }

    @Test
    fun a2Schedule() {
        shotVsCanvas("A2") {
            PemaScaffold(
                topBar = { PemaMainTopBar("Clinic", onRoleClick = {}, unread = 1) },
                bottomBar = { PemaBottomNav(ownerNav, 1, {}) },
            ) { inner ->
                Column(Modifier.fillMaxSize().padding(inner).padding(start = 20.dp, top = 8.dp, end = 20.dp)) {
                    PemaHeading("Điều phối lịch", "Thứ Ba, 22 tháng 9")
                    WeekStrip()
                    PemaTile("BS. Tâm · Phòng khám 01", "Ca sáng 08:00–12:00", "tune", onClick = {})
                    PemaTile("09:00", "Khung giờ trống", "schedule", onClick = {})
                    PemaTile("10:30", "Nguyễn Thu Hà · Tái khám", "schedule", onClick = {})
                    PemaTile("14:00", "Khung giờ trống", "schedule", onClick = {})
                    PemaPrimary("Đặt / dời lịch", onClick = {})
                }
            }
        }
    }

    @Test
    fun controlsGallery() {
        shotVsCanvas("controls") {
            DetailScaffold("Gửi cập nhật", onBack = {}) {
                PemaNotice("Ảnh chỉ lưu trên thiết bị trong phiên này.")
                PemaSearchField("", {})
                Spacer(Modifier.height(12.dp))
                PemaTextField("Da hơi đỏ nhẹ", {}, label = "Mô tả", minLines = 3)
                Spacer(Modifier.height(12.dp))
                PemaTextField("", {}, label = "Ghi chú")
                Spacer(Modifier.height(12.dp))
                PemaDropdownField("Uống", listOf("Uống", "Bôi"), {}, label = "Đường dùng")
                PemaChipWrap {
                    PemaFilterChip("09:00", selected = true, onClick = {})
                    PemaFilterChip("10:30", selected = false, onClick = {})
                    PemaFilterChip("14:00", selected = false, onClick = {}, enabled = false)
                }
                PemaCheckRow("Đồng ý chia sẻ ảnh", checked = true, onCheckedChange = {})
                PemaCheckRow("Nhắc tôi", checked = false, onCheckedChange = {})
                PemaOutlinedButton("Gọi người bệnh", onClick = {}, icon = "call")
                PemaTextButton("Chụp ảnh", onClick = {}, icon = "photo_camera")
                PemaPrimary("Gửi", onClick = {})
                PemaPrimary("Gửi (tắt)", onClick = null)
                Box(Modifier.height(1.dp))
            }
        }
    }
}
