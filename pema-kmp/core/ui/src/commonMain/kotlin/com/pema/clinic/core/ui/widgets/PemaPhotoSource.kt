package com.pema.clinic.core.ui.widgets

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType

/**
 * Where a clinical photo comes from – on phones the web image file input offers the camera or
 * existing photos. Photos are resized and stripped of location data.
 */
@Composable
fun PemaPhotoSourceSheet(
    title: String,
    onCamera: () -> Unit,
    onGallery: () -> Unit,
    onDismiss: () -> Unit,
) {
    PemaBottomSheet(onDismiss = onDismiss) {
        Text(title, style = PemaType.of(22f, androidx.compose.ui.text.font.FontWeight.W600, PemaColors.Ink), modifier = Modifier.padding(start = 20.dp, end = 20.dp, bottom = 12.dp))
        PemaListRow("Chụp ảnh", onClick = onCamera, leadingIcon = "photo_camera", leadingColor = PemaColors.Blue)
        PemaListRow("Chọn ảnh có sẵn", onClick = onGallery, leadingIcon = "photo_library", leadingColor = PemaColors.Blue)
        PemaNotice(
            "Ảnh được thu nhỏ và bỏ thông tin vị trí trước khi lưu vào hồ sơ.",
            Modifier.padding(start = 20.dp, end = 20.dp, top = 12.dp),
        )
    }
}
