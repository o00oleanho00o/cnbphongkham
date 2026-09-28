package com.pema.clinic.feature.aftercare

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.hardware.CapturedPhoto
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.LocalPemaSnackbar
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.core.ui.widgets.LocalPhoto
import com.pema.clinic.core.ui.widgets.PemaFilledButton
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaIcon
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaTextButton
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.patients.PatientState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

@Immutable
internal data class HomeCareUiState(val acknowledged: Boolean)

@Composable
internal fun HomeCareRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val patients by deps.patientsStore.state.collectAsStateWithLifecycle()
    val profile = deps.catalogRepository.catalog().profiles[session.selected]
    val patient = patients[profile.id] ?: PatientState.fromProfile(profile)
    DetailScaffold(title = Routes.titleOf(Routes.HomeCare)) {
        HomeCareScreen(
            state = HomeCareUiState(patient.acknowledged),
            onAcknowledge = { deps.patientsStore.acknowledgeInstructions(profile.id) },
            onSendUpdate = { deps.navigator.go(Routes.SendUpdate) },
        )
    }
}

@Composable
internal fun HomeCareScreen(
    state: HomeCareUiState,
    onAcknowledge: () -> Unit,
    onSendUpdate: () -> Unit,
) {
    PemaHeading("Nhẹ nhàng với làn da", "Hướng dẫn mẫu đã được bác sĩ kiểm tra")
    listOf(
        "Làm sạch dịu nhẹ",
        "Dưỡng ẩm theo hướng dẫn",
        "Bảo vệ da khỏi ánh nắng",
    ).forEach { title ->
        PemaTile(
            title = title,
            sub = "Thực hiện theo hướng dẫn cá nhân đã duyệt.",
            icon = "favorite_border",
            onClick = null,
        )
    }
    PemaPrimary(
        text = if (state.acknowledged) "Đã xác nhận đã đọc" else "Tôi đã đọc hướng dẫn",
        onClick = if (state.acknowledged) null else onAcknowledge,
    )
    PemaPrimary("Gửi cập nhật cho Pema", onSendUpdate)
}

@Composable
internal fun SendUpdateRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val patientId = deps.catalogRepository.catalog().profiles[session.selected].id
    val draft = remember { SendUpdateDraft() }
    val snackbar = LocalPemaSnackbar.current
    val scope = rememberCoroutineScope()
    val messenger = rememberPemaMessenger()
    val camera = deps.platform.camera
    DisposableEffect(draft, camera) {
        onDispose {
            CoroutineScope(Dispatchers.Default).launch { draft.dispose(camera) }
        }
    }
    DetailScaffold(title = Routes.titleOf(Routes.SendUpdate)) {
        SendUpdateScreen(
            draft = draft,
            onCapture = {
                scope.launch {
                    val message = draft.capture(camera)
                    if (message != null) snackbar.showSnackbar(message)
                }
            },
            onRemovePhoto = { scope.launch { draft.removePhoto(camera) } },
            onSubmit = {
                if (draft.submit(deps.patientsStore, patientId)) {
                    messenger.show("Đã gửi • Chờ đội ngũ xem")
                    deps.navigator.back()
                }
            },
        )
    }
}

@Composable
internal fun SendUpdateScreen(
    draft: SendUpdateDraft,
    onCapture: () -> Unit,
    onRemovePhoto: () -> Unit,
    onSubmit: () -> Unit,
    photoPreview: PhotoPreviewMode = PhotoPreviewMode.LocalPhoto,
) {
    PemaNotice("Cập nhật sẽ vào hàng chờ để đội ngũ Pema xem.")
    PemaTextField(
        value = draft.text,
        onValueChange = { draft.text = it },
        label = "Hôm nay da bạn thế nào?",
        minLines = 5,
        maxLines = 5,
    )
    Spacer(Modifier.height(12.dp))
    val photo = draft.photo
    if (photo != null) {
        when (photoPreview) {
            PhotoPreviewMode.LocalPhoto -> LocalPhoto(path = photo.path, height = 260.dp, label = "Ảnh vừa chụp")
            PhotoPreviewMode.CanvasTile -> CanvasPhotoTile(label = "Ảnh vừa chụp", modifier = Modifier.fillMaxWidth())
            PhotoPreviewMode.CanvasSummary -> PemaFilledButton(
                text = "Đã chọn ảnh mẫu",
                onClick = {},
                modifier = Modifier.padding(vertical = 8.dp).fillMaxWidth(),
            )
        }
        if (photoPreview == PhotoPreviewMode.LocalPhoto || photoPreview == PhotoPreviewMode.CanvasTile) {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                PemaTextButton("Chụp lại", onClick = onCapture, icon = "refresh", enabled = !draft.capturing)
                PemaTextButton("Bỏ ảnh", onClick = onRemovePhoto, icon = "delete", enabled = !draft.capturing)
            }
            PemaNotice("Chụp chính diện, đủ sáng. Ảnh đã được bỏ thông tin vị trí.")
        } else {
            PemaNotice("Ảnh mẫu dùng duyệt UI • camera native chưa kết nối")
        }
        AftercareCheckRow(
            label = "Tôi đồng ý chia sẻ ảnh để chăm sóc",
            checked = draft.consent,
            onCheckedChange = { draft.consent = it },
        )
    } else {
        CapturePhotoButton(capturing = draft.capturing, onClick = onCapture)
    }
    PemaPrimary("Gửi cập nhật", if (draft.canSend) onSubmit else null)
}

@Composable
private fun CapturePhotoButton(capturing: Boolean, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        enabled = !capturing,
        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color.White, contentColor = PemaColors.Blue),
        border = androidx.compose.foundation.BorderStroke(1.dp, PemaColors.FieldBorder),
        contentPadding = PaddingValues(horizontal = 16.dp),
    ) {
        if (capturing) {
            CircularProgressIndicator(Modifier.size(18.dp), color = PemaColors.Blue, strokeWidth = 2.dp)
        } else {
            PemaIcon("photo_camera", size = 18.dp)
        }
        Spacer(Modifier.width(8.dp))
        Text("Chụp ảnh tiến triển", style = PemaType.label)
    }
}

@Composable
internal fun FollowUpReplyRoute(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val patients by deps.patientsStore.state.collectAsStateWithLifecycle()
    val profile = deps.catalogRepository.catalog().profiles[session.selected]
    val patient = patients[profile.id] ?: PatientState.fromProfile(profile)
    var reply by remember { mutableStateOf("") }
    val messenger = rememberPemaMessenger()
    DetailScaffold(title = Routes.titleOf(Routes.FollowUpReply)) {
        FollowUpReplyScreen(
            profile = profile,
            patient = patient,
            reply = reply,
            onReplyChange = { reply = it },
            onSubmit = {
                deps.patientsStore.submitDoctorReply(profile.id, reply)
                messenger.show("Đã gửi phản hồi sang Pema Care")
                deps.navigator.back()
            },
        )
    }
}

@Composable
internal fun FollowUpReplyScreen(
    profile: PatientProfile,
    patient: PatientState,
    reply: String,
    onReplyChange: (String) -> Unit,
    onSubmit: () -> Unit,
) {
    patient.escalations.forEach { PemaNotice("CSKH bàn giao nội bộ: $it") }
    PemaHeading(profile.name, "Cập nhật từ Patient Mobile")
    patient.updates.forEach { PemaNotice(it) }
    if (patient.photos.isNotEmpty()) {
        Row(
            Modifier.fillMaxWidth().height(160.dp).horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            patient.photos.forEachIndexed { index, path ->
                LocalPhoto(
                    path = path,
                    height = 160.dp,
                    label = "Ảnh ${index + 1}",
                    modifier = Modifier.width(120.dp),
                )
            }
        }
        Spacer(Modifier.height(16.dp))
    }
    PemaTextField(
        value = reply,
        onValueChange = onReplyChange,
        label = "Phản hồi đã kiểm tra",
        minLines = 5,
        maxLines = 5,
    )
    PemaPrimary("Duyệt và phản hồi", if (canSendReply(reply)) onSubmit else null)
}

@Composable
internal fun PrivacyRoute() {
    var consent by remember { mutableStateOf(false) }
    DetailScaffold(title = Routes.titleOf(Routes.Privacy)) {
        PrivacyScreen(consent = consent, onConsentChange = { consent = it })
    }
}

@Composable
internal fun PrivacyScreen(consent: Boolean, onConsentChange: (Boolean) -> Unit) {
    PemaNotice("Template không sử dụng dữ liệu bệnh nhân thật.")
    AftercareCheckRow("Đồng ý dùng ảnh trong chăm sóc", checked = consent, onCheckedChange = onConsentChange)
    Text("Cài đặt đang được minh họa trong phiên duyệt.", style = PemaType.body)
}

@Composable
private fun AftercareCheckRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    val longLabel = label.length >= 34
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 56.dp)
            .toggleable(value = checked, role = Role.Checkbox, onValueChange = onCheckedChange)
            .padding(start = 16.dp, end = if (longLabel) 4.dp else 24.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Start,
    ) {
        if (longLabel) {
            Text("Tôi đồng ý chia sẻ ảnh để chăm", style = PemaType.input, maxLines = 1, overflow = TextOverflow.Visible)
            Text(" sóc", style = PemaType.input, maxLines = 1, overflow = TextOverflow.Visible)
            Spacer(Modifier.weight(1f))
        } else {
            Text(
                label,
                style = PemaType.input,
                modifier = Modifier.weight(1f),
                maxLines = 1,
                overflow = TextOverflow.Visible,
            )
            Spacer(Modifier.width(16.dp))
        }
        Box(
            Modifier
                .size(18.dp)
                .then(
                    if (checked) {
                        Modifier.background(PemaColors.Blue, RoundedCornerShape(2.dp))
                    } else {
                        Modifier.border(2.dp, PemaColors.OnSurfaceVariant, RoundedCornerShape(2.dp))
                    },
                ),
            contentAlignment = Alignment.Center,
        ) {
            if (checked) PemaIcon("check", size = 16.dp, color = Color.White)
        }
    }
}

internal enum class PhotoPreviewMode { LocalPhoto, CanvasTile, CanvasSummary }

@Composable
internal fun CanvasPhotoTile(label: String, modifier: Modifier = Modifier, height: Dp = 220.dp) {
    Column(
        modifier
            .padding(4.dp)
            .height(height)
            .clip(RoundedCornerShape(18.dp))
            .background(PemaColors.Tint)
            .border(0.dp, Color.Transparent, RoundedCornerShape(18.dp))
            .padding(8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        PemaIcon("face", size = 76.dp, color = PemaColors.PhotoIcon)
        Text(label, style = PemaType.of(14f, FontWeight.W400, PemaColors.OnSurface))
        Text("Minh họa", style = PemaType.of(11f, FontWeight.W400, PemaColors.OnSurface))
    }
}

internal fun sampleCapturedPhoto(path: String = "sample://aftercare.jpg") =
    CapturedPhoto(path = path, width = 1200, height = 1600, bytes = 240_000)
