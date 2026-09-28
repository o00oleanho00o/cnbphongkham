package com.pema.clinic.feature.care

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.PemaBottomSheet
import com.pema.clinic.core.ui.widgets.PemaEmpty
import com.pema.clinic.core.ui.widgets.PemaH2
import com.pema.clinic.core.ui.widgets.PemaIcon
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.care.CareCase
import com.pema.clinic.shared.care.CareQueueFilter
import com.pema.clinic.shared.care.careBuckets
import com.pema.clinic.shared.care.careGroups
import com.pema.clinic.shared.care.careNotContacted

private val Radius16 = RoundedCornerShape(16.dp)
private val Radius18 = RoundedCornerShape(18.dp)

// Android can only save Bundle types; store the filter as its three strings.
private val CareQueueFilterSaver = listSaver<CareQueueFilter, String>(
    save = { listOf(it.group, it.query, it.bucket) },
    restore = { CareQueueFilter(group = it[0], query = it[1], bucket = it[2]) },
)

@Composable
fun CareQueue(deps: FeatureDeps, onOpen: () -> Unit, modifier: Modifier = Modifier) {
    val cases by deps.careQueue.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    var filter by rememberSaveable(stateSaver = CareQueueFilterSaver) { mutableStateOf(CareQueueFilter()) }
    var searchText by rememberSaveable { mutableStateOf("") }
    var sheetOpen by remember { mutableStateOf(false) }

    CareQueueContent(
        cases = cases,
        staffName = session.staffName,
        filter = filter,
        searchText = searchText,
        onBucketChange = { filter = filter.copy(bucket = it) },
        onSearchChange = {
            searchText = it
            filter = filter.copy(query = it.trim().lowercase())
        },
        onFilterClick = { sheetOpen = true },
        onClearGroup = { filter = filter.copy(group = "all") },
        onOpenProfile = { patientId ->
            deps.sessionStore.select(deps.catalogRepository.catalog().indexOf(patientId))
            onOpen()
        },
        modifier = modifier,
    )

    if (sheetOpen) {
        PemaBottomSheet(onDismiss = { sheetOpen = false }) {
            CareGroupSheetContent(
                cases = cases,
                selectedGroup = filter.group,
                onSelect = {
                    filter = filter.copy(group = it)
                    sheetOpen = false
                },
            )
        }
    }
}

@Composable
internal fun CareQueueContent(
    cases: List<CareCase>,
    staffName: String,
    filter: CareQueueFilter,
    searchText: String,
    onBucketChange: (String) -> Unit,
    onSearchChange: (String) -> Unit,
    onFilterClick: () -> Unit,
    onClearGroup: () -> Unit,
    onOpenProfile: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val rows = cases.filter { it.status == filter.bucket && it.inGroup(filter.group) && it.matches(filter.query) }
    Column(modifier, verticalArrangement = Arrangement.Top) {
        PemaH2("CSKH hôm nay", "$staffName · Chủ nhật, 20/09")
        CareBuckets(cases = cases, selectedBucket = filter.bucket, onBucketChange = onBucketChange)
        Spacer(Modifier.height(16.dp))
        CareSearchRow(
            value = searchText,
            onValueChange = onSearchChange,
            active = filter.group != "all",
            onFilterClick = onFilterClick,
        )
        if (filter.group != "all") {
            CareInputChip(careGroups.getValue(filter.group), onDelete = onClearGroup)
        }
        CareListHead(
            title = if (filter.bucket == careNotContacted) "Danh sách cần chăm sóc" else filter.bucket,
            count = "${rows.size} khách",
        )
        if (rows.isEmpty()) {
            PemaEmpty("Không có khách trong bộ lọc này")
        } else {
            rows.forEach { case ->
                CareRow(case = case, onClick = { onOpenProfile(case.profile.id) })
            }
        }
    }
}

@Composable
private fun CareBuckets(cases: List<CareCase>, selectedBucket: String, onBucketChange: (String) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        careBuckets.forEach { (bucket, label) ->
            val selected = bucket == selectedBucket
            Column(
                Modifier
                    .weight(1f)
                    .clip(Radius16)
                    .background(if (selected) PemaColors.Blue else PemaColors.White)
                    .clickable { onBucketChange(bucket) }
                    .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                Text(
                    "${cases.count { it.status == bucket }}",
                    style = PemaType.of(
                        25f,
                        FontWeight.W700,
                        if (selected) PemaColors.White else PemaColors.Ink,
                        height = 1.1f,
                    ),
                )
                Text(
                    label,
                    style = PemaType.of(
                        11f,
                        FontWeight.W500,
                        if (selected) PemaColors.White else PemaColors.Muted,
                        height = 1.4f,
                    ),
                )
            }
        }
    }
}

@Composable
private fun CareSearchRow(
    value: String,
    onValueChange: (String) -> Unit,
    active: Boolean,
    onFilterClick: () -> Unit,
) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        val fieldShape = RoundedCornerShape(14.dp)
        Row(
            Modifier
                .weight(1f)
                .height(48.dp)
                .background(PemaColors.White, fieldShape)
                .border(1.dp, PemaColors.FieldBorder, fieldShape)
                .padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            PemaIcon("search", size = 21.dp, color = PemaColors.OnSurfaceVariant)
            Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
                BasicTextField(
                    value = value,
                    onValueChange = onValueChange,
                    singleLine = true,
                    textStyle = PemaType.of(13f, color = PemaColors.OnSurface),
                    cursorBrush = SolidColor(PemaColors.Blue),
                    modifier = Modifier.fillMaxWidth(),
                )
                if (value.isEmpty()) {
                    Text(
                        "Tìm tên hoặc mã hồ sơ",
                        style = PemaType.of(13f, color = PemaColors.OnSurfaceVariant),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
        val buttonShape = RoundedCornerShape(14.dp)
        Box(
            Modifier
                .size(48.dp)
                .background(if (active) PemaColors.FilterActive else PemaColors.White, buttonShape)
                .border(1.dp, PemaColors.Line, buttonShape)
                .clip(buttonShape)
                .semantics { contentDescription = "Lọc nhóm chăm sóc" }
                .clickable(onClick = onFilterClick),
            contentAlignment = Alignment.Center,
        ) {
            PemaIcon("tune", size = 22.dp, color = PemaColors.Blue)
            if (active) {
                Box(
                    Modifier
                        .align(Alignment.TopEnd)
                        .padding(top = 11.dp, end = 11.dp)
                        .size(6.dp)
                        .background(PemaColors.Error, CircleShape),
                )
            }
        }
    }
}

@Composable
private fun CareInputChip(label: String, onDelete: () -> Unit) {
    Row(Modifier.padding(top = 10.dp)) {
        Row(
            Modifier
                .height(32.dp)
                .border(1.dp, PemaColors.OutlineVariant, RoundedCornerShape(8.dp))
                .clip(RoundedCornerShape(8.dp))
                .clickable(onClick = onDelete)
                .padding(start = 12.dp, end = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(label, style = PemaType.of(12f, FontWeight.W500, PemaColors.OnSurfaceVariant))
            PemaIcon("close", size = 18.dp, color = PemaColors.OnSurfaceVariant)
        }
    }
}

@Composable
private fun CareListHead(title: String, count: String) {
    Row(
        Modifier.fillMaxWidth().padding(top = 20.dp, bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            title,
            modifier = Modifier.weight(1f),
            style = PemaType.of(14f, FontWeight.W600, PemaColors.Ink),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(count, style = PemaType.of(12f, color = PemaColors.Muted))
    }
}

@Composable
private fun CareRow(case: CareCase, onClick: () -> Unit) {
    val profile = case.profile
    Row(
        Modifier
            .padding(bottom = 10.dp)
            .fillMaxWidth()
            .clip(Radius18)
            .background(PemaColors.White)
            .border(1.dp, PemaColors.Line, Radius18)
            .clickable(onClick = onClick)
            .padding(14.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier.size(40.dp).background(PemaColors.CareAvatar, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Text(profile.initials, style = PemaType.of(13f, FontWeight.W600, PemaColors.Blue))
        }
        Column(Modifier.weight(1f)) {
            Text(
                profile.name,
                style = PemaType.of(14f, FontWeight.W600, PemaColors.Ink, height = 1.4f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                careGroups.getValue(profile.careGroup),
                style = PemaType.of(12f, color = PemaColors.Blue, height = 1.4f),
                modifier = Modifier.padding(top = 5.dp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "${profile.id} · ${profile.doctor}",
                style = PemaType.of(11f, color = PemaColors.Muted, height = 1.4f),
                modifier = Modifier.padding(top = 7.dp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        PemaIcon("chevron_right", size = 20.dp, color = PemaColors.Muted, modifier = Modifier.padding(top = 4.dp))
    }
}

@Composable
internal fun CareGroupSheetContent(
    cases: List<CareCase>,
    selectedGroup: String,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 16.dp)) {
        Text("Nhóm chăm sóc", style = PemaType.of(22f, FontWeight.W700, PemaColors.Ink, height = 1.3f))
        Text(
            "Chọn nhóm để tập trung xử lý",
            style = PemaType.of(14f, color = PemaColors.Muted),
            modifier = Modifier.padding(top = 4.dp),
        )
        Spacer(Modifier.height(16.dp))
        val rows = listOf("all" to "Tất cả nhóm") + careGroups.entries.map { it.key to it.value }
        rows.forEach { (key, label) ->
            val selected = selectedGroup == key
            Row(
                Modifier
                    .fillMaxWidth()
                    .height(56.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .clickable { onSelect(key) }
                    .padding(horizontal = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                PemaIcon(
                    if (selected) "radio_button_checked" else "radio_button_unchecked",
                    size = 21.dp,
                    color = if (selected) PemaColors.Blue else PemaColors.Muted,
                )
                Text(
                    label,
                    modifier = Modifier.weight(1f),
                    style = PemaType.of(14f, color = if (selected) PemaColors.Blue else PemaColors.Ink),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text("${cases.count { it.inGroup(key) }}", style = PemaType.of(14f, color = PemaColors.Muted))
            }
        }
    }
}
