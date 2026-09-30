package com.pema.clinic.feature.finance

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.IconButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.core.ui.widgets.LocalPemaSnackbar
import com.pema.clinic.core.ui.widgets.PemaBadge
import com.pema.clinic.core.ui.widgets.PemaBottomNav
import com.pema.clinic.core.ui.widgets.PemaDialog
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.PemaExtendedFab
import com.pema.clinic.core.ui.widgets.PemaFilledButton
import com.pema.clinic.core.ui.widgets.PemaIcon
import com.pema.clinic.core.ui.widgets.PemaNavItem
import com.pema.clinic.core.ui.widgets.PemaPillButton
import com.pema.clinic.core.ui.widgets.PemaScaffold
import com.pema.clinic.core.ui.widgets.PemaTextButton
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTopBar
import com.pema.clinic.core.ui.widgets.pemaNavigationBars
import com.pema.clinic.shared.finance.FinanceSnapshot
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.finance.ProcedureRow
import com.pema.clinic.shared.util.money
import kotlinx.coroutines.launch
import kotlin.time.Clock
import kotlin.time.ExperimentalTime

internal val statusLabels = mapOf(
    "open" to "Đang đối soát",
    "closed" to "Đã chốt",
    "paid" to "Đã chi",
    "pending" to "Chờ duyệt",
    "approved" to "Đã duyệt",
    "void" to "Đã hủy",
)

private val roleOptions = listOf(
    "owner:D0" to "BS. Tâm · Chủ phòng khám",
    "accountant:D0" to "Kế toán",
    "doctor:D0" to "BS. Tâm · Cá nhân",
    "doctor:D1" to "BS. Mai · Cá nhân",
    "doctor:D2" to "BS. An · Cá nhân",
    "doctor:D3" to "BS. Lan · Cá nhân",
)

@Immutable
internal data class FinanceCallbacks(
    val refresh: () -> Unit = {},
    val selectRole: (String) -> Unit = {},
    val setMonth: (String) -> Unit = {},
    val approveEntry: suspend (String) -> Boolean = { false },
    val voidEntry: suspend (String, String) -> Boolean = { _, _ -> false },
    val recordPayment: suspend (String, String, Int) -> Boolean = { _, _, _ -> false },
    val closePeriod: suspend () -> Boolean = { false },
    val markPeriodPaid: suspend (String) -> Boolean = { false },
    val markNotificationRead: suspend (String) -> Boolean = { false },
    val openProcedureForm: () -> Unit = {},
    val openRateScreen: () -> Unit = {},
)

@Immutable
internal data class FinanceLineData(val label: String, val value: String)

internal fun overviewLines(state: FinanceState, snapshot: FinanceSnapshot): List<FinanceLineData> = buildList {
    if (!state.private) {
        add(FinanceLineData("Thực thu trong tháng", money(snapshot.summary.collected ?: 0)))
        add(FinanceLineData("Công nợ hiện tại", money(snapshot.summary.debt ?: 0)))
    }
    add(FinanceLineData("Tiền thủ thuật đã duyệt", money(snapshot.summary.fee)))
    add(FinanceLineData("Tiền chờ duyệt", money(snapshot.summary.pending)))
}

@Composable
internal fun FinanceScreen(
    state: FinanceState,
    initialTab: Int = 0,
    lockRole: Boolean = false,
    patientIds: List<String>? = null,
    callbacks: FinanceCallbacks = FinanceCallbacks(),
) {
    val scope = rememberCoroutineScope()
    val snackbar = LocalPemaSnackbar.current
    var tab by rememberSaveable(initialTab) { mutableStateOf(initialTab.coerceIn(0, 3)) }
    var ask by remember { mutableStateOf<AskRequest?>(null) }
    var paymentKey by remember { mutableStateOf(paymentKeyNow()) }
    val data = state.data

    fun runCommand(command: suspend () -> Boolean) {
        scope.launch {
            if (command()) snackbar.showSnackbar("Đã ghi nhận thành công")
        }
    }

    fun askFor(title: String, initial: String = "", onConfirm: (String) -> Unit) {
        ask = AskRequest(title, initial, onConfirm)
    }

    PemaScaffold(
        topBar = {
            FinanceTopBar(
                title = "Tài chính Pema",
                onRefresh = callbacks.refresh,
                showRefresh = true,
            )
        },
        bottomBar = {
            FinanceBottomNav(
                selectedIndex = tab,
                unread = state.unread,
                onSelect = { tab = it },
            )
        },
        floatingActionButton = {
            if (tab == 1 && !state.private && (data?.periodOpen == true)) {
                PemaExtendedFab(
                    text = "Ghi lượt",
                    onClick = callbacks.openProcedureForm,
                    modifier = Modifier.padding(end = 16.dp),
                )
            }
        },
    ) { inner ->
        FinanceBody(inner) {
            Text(
                "Vai trò mẫu • dữ liệu dùng chung với web",
                style = PemaType.of(12f, color = PemaColors.Muted),
            )
            Spacer(Modifier.height(8.dp))
            if (!lockRole) {
                val value = "${state.role}:${state.doctor}"
                PemaDropdownField(
                    value = value,
                    options = roleOptions.map { it.first },
                    onSelected = {
                        tab = 0
                        callbacks.selectRole(it)
                    },
                    enabled = !state.sending,
                    display = { selected -> roleOptions.firstOrNull { it.first == selected }?.second ?: selected },
                )
                Spacer(Modifier.height(12.dp))
            }
            PeriodRow(
                month = state.month,
                status = data?.periodStatus,
                onMonthClick = { askFor("Kỳ (yyyy-MM)", state.month, callbacks.setMonth) },
            )
            if (state.error.isNotEmpty()) {
                FinanceCard {
                    Text(
                        state.error,
                        style = PemaType.of(14f, color = Color(0xFFFF5722)),
                    )
                    PemaTextButton("Thử lại", onClick = callbacks.refresh)
                }
            }
            if (data == null && state.error.isEmpty()) {
                Box(Modifier.fillMaxWidth().padding(top = 32.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = PemaColors.Blue)
                }
            }
            if (data != null) {
                when (tab) {
                    0 -> OverviewTab(
                        state = state,
                        snapshot = data,
                        onRates = callbacks.openRateScreen,
                    )
                    1 -> ProceduresTab(
                        state = state,
                        snapshot = data,
                        onApprove = { id -> runCommand { callbacks.approveEntry(id) } },
                        onVoid = { row ->
                            askFor("Lý do hủy") { reason ->
                                runCommand { callbacks.voidEntry(row.id, reason) }
                            }
                        },
                        onClose = {
                            askFor("Gõ CHOT để khóa kỳ ${state.month}") { result ->
                                if (result == "CHOT") runCommand(callbacks.closePeriod)
                            }
                        },
                        onPaid = {
                            askFor("Mã chứng từ chi") { reference ->
                                runCommand { callbacks.markPeriodPaid(reference) }
                            }
                        },
                    )
                    2 -> PaymentsTab(
                        state = state,
                        snapshot = data,
                        onCollect = { invoice ->
                            askFor("Số tiền mặt thu (VND)") { text ->
                                val amount = text.toIntOrNull() ?: return@askFor
                                scope.launch {
                                    val ok = callbacks.recordPayment("APP-$paymentKey", invoice.id, amount)
                                    if (ok) {
                                        paymentKey = paymentKeyNow()
                                        snackbar.showSnackbar("Đã thu và thông báo chủ phòng khám")
                                    }
                                }
                            }
                        },
                    )
                    else -> NotificationsTab(
                        state = state,
                        snapshot = data,
                        onRead = { id -> runCommand { callbacks.markNotificationRead(id) } },
                    )
                }
            }
        }
    }
    ask?.let { request ->
        AskDialog(
            request = request,
            onDismiss = { ask = null },
        )
    }
}

@Composable
private fun FinanceBody(
    inner: PaddingValues,
    content: @Composable ColumnScope.() -> Unit,
) {
    Box(Modifier.fillMaxSize().padding(inner), contentAlignment = Alignment.TopCenter) {
        Column(
            Modifier
                .widthIn(max = 720.dp)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .windowInsetsPadding(pemaNavigationBars.only(WindowInsetsSides.Bottom))
                .padding(20.dp),
            content = content,
        )
    }
}

@Composable
internal fun FinanceDetailScaffold(
    title: String,
    actions: @Composable RowScope.() -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    PemaScaffold(
        topBar = { FinanceTopBar(title = title, showRefresh = false, actions = actions) },
    ) { inner ->
        Box(Modifier.fillMaxSize().padding(inner), contentAlignment = Alignment.TopCenter) {
            Column(
                Modifier
                    .widthIn(max = 720.dp)
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(20.dp),
                content = content,
            )
        }
    }
}

@Composable
private fun FinanceTopBar(
    title: String,
    onRefresh: () -> Unit = {},
    showRefresh: Boolean,
    actions: @Composable RowScope.() -> Unit = {},
) {
    PemaTopBar(
        title = {
            Text(
                title,
                style = PemaType.of(22f, FontWeight.W400, PemaColors.Ink, height = 1.3f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        },
        onBack = LocalOnBack.current,
        actions = {
            actions()
            if (showRefresh) {
                IconButton(onClick = onRefresh) {
                    PemaIcon("refresh", size = 24.dp, color = PemaColors.Ink, contentDescription = "Làm mới")
                }
            }
        },
    )
}

@Composable
private fun FinanceBottomNav(
    selectedIndex: Int,
    unread: Int,
    onSelect: (Int) -> Unit,
) {
    PemaBottomNav(
        selectedIndex = selectedIndex,
        onSelect = onSelect,
        items = listOf(
            PemaNavItem("Tổng quan", "dashboard", "dashboard"),
            PemaNavItem("Thủ thuật", "receipt_long", "receipt_long"),
            PemaNavItem("Thu tiền", "payments", "payments"),
            PemaNavItem("Thông báo", "notifications", "notifications", badge = unread.takeIf { it > 0 }?.toString()),
        ),
    )
}

@Composable
private fun PeriodRow(
    month: String,
    status: String?,
    onMonthClick: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PemaTextButton("Kỳ $month", onClick = onMonthClick, icon = "calendar_month")
        if (status != null) {
            Text(statusLabels.getValue(status), style = PemaType.of(12f, color = PemaColors.Ink))
        }
    }
}

@Composable
private fun OverviewTab(
    state: FinanceState,
    snapshot: FinanceSnapshot,
    onRates: () -> Unit,
) {
    val summary = snapshot.summary
    FinanceHero(
        over = if (state.private) "DOANH SỐ CỦA TÔI" else "DOANH SỐ THỰC HIỆN",
        value = money(summary.revenue),
    )
    FinanceCard {
        FinanceTitle("Dòng tiền & đối soát")
        overviewLines(state, snapshot).forEach { FinanceLine(it.label, it.value) }
        Text(
            "Tiền thủ thuật không phải lợi nhuận. Công nợ là toàn bộ số còn phải thu.",
            style = PemaType.of(12f, color = PemaColors.Muted),
        )
    }
    if (!state.private) {
        FinanceCard {
            FinanceTitle("Đội ngũ")
            snapshot.doctors.forEach { doctor ->
                FinanceLine(doctor.name, money(snapshot.revenueOf(doctor.id)))
            }
        }
        PemaPillButton(
            text = "Chính sách tỷ lệ thủ thuật",
            onClick = onRates,
            icon = "tune",
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun ProceduresTab(
    state: FinanceState,
    snapshot: FinanceSnapshot,
    onApprove: (String) -> Unit,
    onVoid: (ProcedureRow) -> Unit,
    onClose: () -> Unit,
    onPaid: () -> Unit,
) {
    FinanceTitle("Từng lượt, từng người thực hiện")
    Text(
        "Tỷ lệ lưu theo lượt; kế toán đối soát trước khi chốt.",
        style = PemaType.of(12f, color = PemaColors.Ink),
    )
    Spacer(Modifier.height(12.dp))
    if (snapshot.rows.isEmpty()) {
        FinanceCard { Text("Chưa có lượt trong kỳ này.", style = PemaType.body) }
    }
    snapshot.rows.forEach { row ->
        FinanceCard {
            FinanceTitle(row.service)
            Text("${row.date} · ${row.patient} · ${snapshot.doctorName(row.doctor)}", style = PemaType.body)
            FinanceLine("Doanh số phân bổ", money(row.revenue))
            FinanceLine("${money(row.base)} × ${row.ratePercent}%", money(row.fee))
            Text(statusLabels.getValue(row.status), style = PemaType.body)
            if (!state.private && snapshot.periodOpen && !row.isVoid) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (row.isPending) {
                        PemaTextButton("Duyệt", onClick = { onApprove(row.id) }, enabled = !state.sending)
                    }
                    PemaTextButton("Hủy lượt", onClick = { onVoid(row) }, enabled = !state.sending)
                }
            }
        }
    }
    if (!state.private && snapshot.periodOpen) {
        PemaPillButton(
            text = "Chốt tháng đã kết thúc",
            onClick = onClose,
            enabled = !state.sending,
            modifier = Modifier.fillMaxWidth(),
        )
    }
    if (!state.private && snapshot.periodClosed) {
        PemaPillButton(
            text = "Xác nhận đã chi",
            onClick = onPaid,
            enabled = !state.sending,
            modifier = Modifier.fillMaxWidth(),
        )
    }
    Spacer(Modifier.height(70.dp))
}

@Composable
private fun PaymentsTab(
    state: FinanceState,
    snapshot: FinanceSnapshot,
    onCollect: (com.pema.clinic.shared.finance.FinanceInvoice) -> Unit,
) {
    if (state.private) {
        FinanceCard {
            Text("Bác sĩ chỉ xem doanh số và tiền thủ thuật của mình.", style = PemaType.body)
        }
        return
    }
    FinanceTitle("Khoản còn phải thu")
    Text(
        "Thu ngân web cũ đồng bộ riêng. Chỉ thu hóa đơn tài chính tại đây.",
        style = PemaType.of(12f, color = PemaColors.Ink),
    )
    Spacer(Modifier.height(12.dp))
    snapshot.receivable.forEach { invoice ->
        FinanceCard {
            FinanceTitle(invoice.patient)
            Text(invoice.id, style = PemaType.body, maxLines = 1, overflow = TextOverflow.Ellipsis)
            FinanceLine("Còn lại", money(invoice.due))
            PemaFilledButton(
                text = "Thu tiền mặt",
                onClick = { onCollect(invoice) },
                enabled = !state.sending,
            )
        }
    }
    if (snapshot.receivable.isEmpty()) {
        FinanceCard { Text("Không còn hóa đơn chờ thu.", style = PemaType.body) }
    }
}

@Composable
private fun NotificationsTab(
    state: FinanceState,
    snapshot: FinanceSnapshot,
    onRead: (String) -> Unit,
) {
    FinanceTitle("Thanh toán mới")
    if (state.role != "owner") {
        FinanceCard {
            Text("Inbox này dành cho chủ phòng khám.", style = PemaType.body)
        }
    } else {
        if (snapshot.notifications.isEmpty()) {
            FinanceCard {
                Text("Thanh toán thành công sẽ xuất hiện ở đây khi app đang mở.", style = PemaType.body)
            }
        }
        snapshot.notifications.forEach { notification ->
            FinanceCard {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    PemaIcon("payments", size = 24.dp, color = PemaColors.Blue)
                    Text(notification.title, style = PemaType.bodyStrong, modifier = Modifier.weight(1f))
                }
                Spacer(Modifier.height(10.dp))
                Text(notification.body, style = PemaType.body)
                Text(notification.shortTime, style = PemaType.of(11f, color = PemaColors.Ink))
                if (!notification.read) {
                    PemaTextButton("Đánh dấu đã đọc", onClick = { onRead(notification.id) }, enabled = !state.sending)
                }
            }
        }
    }
    Text(
        "Đồng bộ khi ứng dụng đang mở; push nền chưa được cấu hình.",
        style = PemaType.of(11f, color = PemaColors.Muted),
    )
}

@Composable
internal fun FinanceHero(over: String, value: String, modifier: Modifier = Modifier) {
    Column(
        modifier
            .fillMaxWidth()
            .padding(bottom = 18.dp)
            .clip(RoundedCornerShape(24.dp))
            .background(
                Brush.linearGradient(
                    colors = listOf(PemaColors.Navy, PemaColors.Blue),
                    start = Offset.Zero,
                    end = Offset.Infinite,
                ),
            )
            .padding(22.dp),
    ) {
        Text(over, style = PemaType.of(11f, color = PemaColors.HeroKicker))
        Spacer(Modifier.height(12.dp))
        Text(value, style = PemaType.of(28f, FontWeight.W700, Color.White, height = 1.3f))
        Spacer(Modifier.height(8.dp))
        Text("Ghi nhận theo lượt hoàn tất", style = PemaType.of(14f, color = Color.White.copy(alpha = 0.7f)))
    }
}

@Composable
internal fun FinanceCard(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier
            .fillMaxWidth()
            .padding(bottom = 16.dp)
            .background(Color.White, RoundedCornerShape(18.dp))
            .border(1.dp, PemaColors.FieldBorderDefault, RoundedCornerShape(18.dp))
            .padding(18.dp),
        horizontalAlignment = Alignment.Start,
        content = content,
    )
}

@Composable
internal fun FinanceTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        style = PemaType.financeTitle,
        modifier = modifier.padding(bottom = 12.dp),
    )
}

@Composable
internal fun FinanceLine(label: String, value: String, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Text(label, style = PemaType.body, modifier = Modifier.weight(1f))
        Text(value, style = PemaType.bodyStrong, maxLines = 1)
    }
}

@Composable
internal fun MaterialRateCard(
    title: String,
    subtitle: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier
            .fillMaxWidth()
            .padding(4.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        color = PemaColors.SurfaceContainerLow,
        contentColor = PemaColors.OnSurface,
        shadowElevation = 3.dp,
        tonalElevation = 0.dp,
        border = BorderStroke(0.dp, Color.Transparent),
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .heightIn(min = 72.dp)
                .padding(start = 16.dp, top = 8.dp, end = 24.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Column(Modifier.weight(1f)) {
                Text(title, style = PemaType.of(16f, color = PemaColors.OnSurface, height = 24f / 16f))
                Text(subtitle, style = PemaType.of(14f, color = PemaColors.OnSurfaceVariant, height = 20f / 14f))
            }
            PemaIcon("edit", size = 24.dp, color = PemaColors.OnSurfaceVariant)
        }
    }
}

@Immutable
private data class AskRequest(
    val title: String,
    val initial: String = "",
    val onConfirm: (String) -> Unit,
)

@Composable
private fun AskDialog(
    request: AskRequest,
    onDismiss: () -> Unit,
) {
    var input by remember(request) { mutableStateOf(request.initial) }
    PemaDialog(
        title = request.title,
        onDismiss = onDismiss,
        confirmText = "Xác nhận",
        onConfirm = {
            val text = input.trim()
            if (text.isNotEmpty()) {
                onDismiss()
                request.onConfirm(text)
            }
        },
        dismissText = "Quay lại",
    ) {
        PemaTextField(
            value = input,
            onValueChange = { input = it },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
        )
    }
}

@OptIn(ExperimentalTime::class)
private fun paymentKeyNow(): String = Clock.System.now().toEpochMilliseconds().toString()
