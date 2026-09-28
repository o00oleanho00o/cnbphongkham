package com.pema.clinic.feature.orders

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.moneyFormat
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.PemaIcon
import com.pema.clinic.core.ui.widgets.PemaLogo
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaSearchField
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.catalog.Product
import com.pema.clinic.shared.orders.Order
import com.pema.clinic.shared.patients.CartLine
import com.pema.clinic.shared.patients.PatientState
import com.pema.clinic.shared.session.Session
import kotlinx.coroutines.flow.StateFlow

fun NavGraphBuilder.ordersGraph(deps: FeatureDeps) {
    composable(Routes.QuickOrder) {
        val vm = viewModel { OrdersViewModel(deps) }
        QuickOrderRoute(vm)
    }
    composable(Routes.OrderReview) {
        val vm = viewModel { OrdersViewModel(deps) }
        OrderReviewRoute(vm)
    }
    composable(Routes.Prescriptions) {
        val vm = viewModel { OrdersViewModel(deps) }
        PrescriptionsRoute(vm)
    }
    composable(Routes.A5Print) {
        val vm = viewModel { OrdersViewModel(deps) }
        A5PrintRoute(vm)
    }
}

internal class OrdersViewModel(private val deps: FeatureDeps) : ViewModel() {
    val session: StateFlow<Session> = deps.sessionStore.state
    val patients: StateFlow<Map<String, PatientState>> = deps.patientsStore.state
    val orders: StateFlow<List<Order>> = deps.ordersStore.state

    fun quickState(
        session: Session = this.session.value,
        patients: Map<String, PatientState> = this.patients.value,
        filter: String,
    ): QuickOrderUiState {
        val (profile, patient) = deps.currentPatient(session, patients)
        val catalog = deps.catalogRepository.catalog()
        return buildQuickOrderState(profile, patient, catalog.products, filter)
    }

    fun reviewState(
        session: Session = this.session.value,
        patients: Map<String, PatientState> = this.patients.value,
    ): OrderReviewUiState {
        val (profile, patient) = deps.currentPatient(session, patients)
        return buildOrderReviewState(profile, patient)
    }

    fun prescriptionsState(
        session: Session = this.session.value,
        orders: List<Order> = this.orders.value,
    ): PrescriptionsUiState {
        val profile = deps.currentProfile(session)
        return buildPrescriptionsState(session.careMode, profile, orders)
    }

    fun a5State(
        session: Session = this.session.value,
        orders: List<Order> = this.orders.value,
    ): A5PrintUiState {
        val profile = deps.currentProfile(session)
        return buildA5PrintState(profile, orders)
    }

    fun addToCart(product: Product): String {
        deps.patientsStore.addToCart(deps.sessionStore.selectedPatientId(), product)
        return "Đã thêm ${product.code}"
    }

    fun decreaseLine(index: Int) = updateLine(index) { line ->
        line.copy(quantity = (line.quantity - 1).coerceAtLeast(1))
    }

    fun increaseLine(index: Int) = updateLine(index) { it.copy(quantity = it.quantity + 1) }

    fun removeLine(index: Int) {
        deps.patientsStore.removeLine(deps.sessionStore.selectedPatientId(), index)
    }

    fun changeRoute(index: Int, route: String) = updateLine(index) { it.copy(route = route) }

    fun changeUsage(index: Int, usage: String) = updateLine(index) { it.copy(usage = usage) }

    fun saveDraft() {
        deps.ordersStore.save(deps.sessionStore.selectedPatientId(), approve = false)
        deps.navigator.go(Routes.Prescriptions)
    }

    fun approve() {
        deps.ordersStore.save(deps.sessionStore.selectedPatientId(), approve = true)
        deps.navigator.go(Routes.Prescriptions)
    }

    fun edit(order: Order) {
        deps.ordersStore.edit(deps.sessionStore.selectedPatientId(), order)
        deps.navigator.go(Routes.OrderReview)
    }

    fun openReview() = deps.navigator.go(Routes.OrderReview)
    fun openA5Print() = deps.navigator.go(Routes.A5Print)

    private fun updateLine(index: Int, change: (CartLine) -> CartLine) {
        deps.patientsStore.updateLine(deps.sessionStore.selectedPatientId(), index, change)
    }
}

@Immutable
internal data class QuickOrderUiState(
    val title: String = Routes.titleOf(Routes.QuickOrder),
    val patientId: String,
    val patientName: String,
    val catalogCount: Int,
    val cartCount: Int,
    val cartTotal: Int,
    val products: List<Product>,
)

@Immutable
internal data class OrderReviewUiState(
    val title: String = Routes.titleOf(Routes.OrderReview),
    val patientId: String,
    val lines: List<CartLine>,
    val cartTotal: Int,
    val cartReady: Boolean,
) {
    val cartCount: Int get() = lines.size
}

@Immutable
internal data class PrescriptionsUiState(
    val title: String = Routes.titleOf(Routes.Prescriptions),
    val patientId: String,
    val patientName: String,
    val careMode: Boolean,
    val orders: List<Order>,
) {
    val visibleOrders: List<Order> get() = orders.filter { !careMode || it.approved }
}

@Immutable
internal data class A5PrintUiState(
    val title: String = Routes.titleOf(Routes.A5Print),
    val patientName: String,
    val orders: List<Order>,
) {
    val approvedOrders: List<Order> get() = orders.filter { it.approved }
}

internal fun buildQuickOrderState(
    profile: PatientProfile,
    patient: PatientState,
    products: List<Product>,
    filter: String,
): QuickOrderUiState {
    val query = filter.lowercase()
    return QuickOrderUiState(
        patientId = profile.id,
        patientName = profile.name,
        catalogCount = products.size,
        cartCount = patient.cart.size,
        cartTotal = patient.cartTotal,
        products = products.filter { it.matches(query) }.take(20),
    )
}

internal fun buildOrderReviewState(profile: PatientProfile, patient: PatientState): OrderReviewUiState =
    OrderReviewUiState(
        patientId = profile.id,
        lines = patient.cart,
        cartTotal = patient.cartTotal,
        cartReady = patient.cartReady,
    )

internal fun buildPrescriptionsState(careMode: Boolean, profile: PatientProfile, orders: List<Order>): PrescriptionsUiState =
    PrescriptionsUiState(
        patientId = profile.id,
        patientName = profile.name,
        careMode = careMode,
        orders = orders.filter { it.patientId == profile.id },
    )

internal fun buildA5PrintState(profile: PatientProfile, orders: List<Order>): A5PrintUiState =
    A5PrintUiState(
        patientName = profile.name,
        orders = orders.filter { it.patientId == profile.id },
    )

@Composable
private fun QuickOrderRoute(vm: OrdersViewModel) {
    val session by vm.session.collectAsStateWithLifecycle()
    val patients by vm.patients.collectAsStateWithLifecycle()
    var filter by rememberSaveable { mutableStateOf("") }
    val messenger = rememberPemaMessenger()

    QuickOrderScreen(
        state = vm.quickState(session, patients, filter),
        filter = filter,
        onFilterChange = { filter = it.lowercase() },
        onOpenReview = vm::openReview,
        onAddProduct = { product -> messenger.show(vm.addToCart(product)) },
    )
}

@Composable
private fun OrderReviewRoute(vm: OrdersViewModel) {
    val session by vm.session.collectAsStateWithLifecycle()
    val patients by vm.patients.collectAsStateWithLifecycle()
    OrderReviewScreen(
        state = vm.reviewState(session, patients),
        onDecrease = vm::decreaseLine,
        onIncrease = vm::increaseLine,
        onRemove = vm::removeLine,
        onRouteChange = vm::changeRoute,
        onUsageChange = vm::changeUsage,
        onSaveDraft = vm::saveDraft,
        onApprove = vm::approve,
    )
}

@Composable
private fun PrescriptionsRoute(vm: OrdersViewModel) {
    val session by vm.session.collectAsStateWithLifecycle()
    val orders by vm.orders.collectAsStateWithLifecycle()
    PrescriptionsScreen(
        state = vm.prescriptionsState(session, orders),
        onEdit = vm::edit,
        onOpenA5 = vm::openA5Print,
    )
}

@Composable
private fun A5PrintRoute(vm: OrdersViewModel) {
    val session by vm.session.collectAsStateWithLifecycle()
    val orders by vm.orders.collectAsStateWithLifecycle()
    A5PrintPreviewScreen(state = vm.a5State(session, orders))
}

@Composable
internal fun QuickOrderScreen(
    state: QuickOrderUiState,
    filter: String,
    onFilterChange: (String) -> Unit,
    onOpenReview: () -> Unit,
    onAddProduct: (Product) -> Unit,
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = state.title, onBack = onBack) {
        PemaNotice("${state.patientName} · ${state.patientId}\n${state.catalogCount} sản phẩm từ catalog web. Đơn nháp chưa gửi cho người bệnh.")
        PemaSearchField(
            value = filter,
            onValueChange = onFilterChange,
            hint = "Tìm mã hoặc tên sản phẩm",
        )
        Spacer(Modifier.height(12.dp))
        PemaPrimary(
            "Xem đơn · ${state.cartCount} sản phẩm · ${moneyFormat(state.cartTotal)}",
            onClick = if (state.cartCount == 0) null else onOpenReview,
        )
        state.products.forEach { product ->
            PemaTile(
                title = product.name,
                sub = "${product.code} · ${product.unit} · ${moneyFormat(product.price)}\n${if (product.needsClassification) "Cần phân loại" else product.sourceType}",
                icon = "add",
                onClick = { onAddProduct(product) },
            )
        }
    }
}

@Composable
internal fun OrderReviewScreen(
    state: OrderReviewUiState,
    onDecrease: (Int) -> Unit,
    onIncrease: (Int) -> Unit,
    onRemove: (Int) -> Unit,
    onRouteChange: (Int, String) -> Unit,
    onUsageChange: (Int, String) -> Unit,
    onSaveDraft: () -> Unit,
    onApprove: () -> Unit,
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = state.title, onBack = onBack) {
        com.pema.clinic.core.ui.widgets.PemaHeading(
            "Kiểm tra trước khi duyệt",
            "${state.cartCount} dòng · ${moneyFormat(state.cartTotal)}",
        )
        state.lines.forEachIndexed { index, line ->
            OrderLineCard(
                line = line,
                onDecrease = { onDecrease(index) },
                onIncrease = { onIncrease(index) },
                onRemove = { onRemove(index) },
                onRouteChange = { onRouteChange(index, it) },
                onUsageChange = { onUsageChange(index, it) },
            )
        }
        PemaNotice("Tài khoản bác sĩ mô phỏng. Chỉ duyệt khi đã phân loại và nhập hướng dẫn cho mọi dòng.")
        PemaPrimary(
            "Lưu nháp",
            onClick = if (state.lines.isEmpty()) null else onSaveDraft,
        )
        PemaPrimary(
            "Bác sĩ duyệt đơn",
            onClick = if (state.cartReady) onApprove else null,
        )
    }
}

@Composable
internal fun PrescriptionsScreen(
    state: PrescriptionsUiState,
    onEdit: (Order) -> Unit,
    onOpenA5: () -> Unit,
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = state.title, onBack = onBack) {
        PemaNotice(
            if (state.careMode) {
                "Chỉ hiển thị nội dung đã được bác sĩ duyệt."
            } else {
                "Nháp → bác sĩ duyệt → người bệnh xem. In không đồng nghĩa đã cấp thuốc."
            },
        )
        val visible = state.visibleOrders
        if (visible.isEmpty()) {
            PemaTile(
                title = "Chưa có đơn${if (state.careMode) " đã duyệt" else ""}",
                sub = "Đơn mới sẽ xuất hiện tại đây",
                icon = "receipt_long",
                onClick = null,
            )
        }
        visible.forEach { order ->
            PemaSection("${order.id} · ${if (order.approved) "Đã duyệt" else "Nháp"}")
            orderRoutesForSheets.forEach { route ->
                Text(
                    if (route == prescriptionRoute) "Đơn thuốc" else "Phiếu tư vấn",
                    style = PemaType.of(14f, FontWeight.W700, PemaColors.Ink),
                )
                order.items.filter { it.route == route }.forEach { line ->
                    PemaTile(
                        title = line.name,
                        sub = "${line.quantity} ${line.unit} · ${line.usage}",
                        icon = "medication",
                        onClick = null,
                    )
                }
            }
            if (!state.careMode && !order.approved) {
                PemaPrimary("Sửa và duyệt bản nháp", onClick = { onEdit(order) })
            }
            if (!state.careMode) {
                PemaPrimary("Xem bố cục hai phiếu A5", onClick = onOpenA5)
            }
        }
    }
}

@Composable
internal fun A5PrintPreviewScreen(
    state: A5PrintUiState,
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = state.title, onBack = onBack) {
        PemaNotice("Bản duyệt bố cục trên điện thoại. In / chia sẻ PDF native sẽ nối sau khi duyệt template.")
        A5Sheet(
            kind = "ĐƠN THUỐC",
            patientName = state.patientName,
            lines = state.approvedOrders.a5Lines(prescriptionRoute),
            footer = "Mang theo đơn này · Kiểm tra thuốc\nBác sĩ khám",
        )
        A5Sheet(
            kind = "PHIẾU TƯ VẤN",
            patientName = state.patientName,
            lines = state.approvedOrders.a5Lines(consultationRoute),
            footer = "Mang theo phiếu này · Kiểm tra sản phẩm\nBác sĩ tư vấn",
        )
    }
}

@Composable
private fun OrderLineCard(
    line: CartLine,
    onDecrease: () -> Unit,
    onIncrease: () -> Unit,
    onRemove: () -> Unit,
    onRouteChange: (String) -> Unit,
    onUsageChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier
            .fillMaxWidth()
            .padding(4.dp)
            .background(PemaColors.White, RoundedCornerShape(12.dp))
            .padding(16.dp),
    ) {
        Text(line.name, style = PemaType.bodyStrong)
        Row(
            Modifier.height(48.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onDecrease) {
                PemaIcon("remove_circle_outline", size = 24.dp, color = PemaColors.OnSurfaceVariant, contentDescription = "Giảm số lượng")
            }
            Text("${line.quantity} ${line.unit}", style = PemaType.body)
            IconButton(onClick = onIncrease) {
                PemaIcon("add_circle_outline", size = 24.dp, color = PemaColors.OnSurfaceVariant, contentDescription = "Tăng số lượng")
            }
            Spacer(Modifier.weight(1f))
            IconButton(onClick = onRemove) {
                PemaIcon("delete_outline", size = 24.dp, color = PemaColors.OnSurfaceVariant, contentDescription = "Xóa dòng")
            }
        }
        PemaDropdownField(
            value = line.route,
            options = orderRouteOptions,
            onSelected = onRouteChange,
            display = ::orderRouteLabel,
        )
        Spacer(Modifier.height(12.dp))
        PemaTextField(
            value = line.usage,
            onValueChange = onUsageChange,
            label = "Cách dùng / hướng dẫn",
            minLines = if (line.usage.length > 28) 2 else 1,
            maxLines = 3,
        )
    }
}

@Composable
private fun A5Sheet(
    kind: String,
    patientName: String,
    lines: List<String>,
    footer: String,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier
            .fillMaxWidth()
            .padding(4.dp)
            .background(PemaColors.White, RoundedCornerShape(12.dp))
            .padding(24.dp),
    ) {
        PemaLogo(width = 90.dp)
        PemaSection(kind)
        Text(patientName, style = PemaType.body)
        A5Divider()
        lines.forEach { text ->
            Text(
                text,
                style = PemaType.body,
                modifier = Modifier.padding(vertical = 8.dp),
            )
        }
        A5Divider()
        Text(footer, style = PemaType.body)
        Spacer(Modifier.height(32.dp))
        Text("BS. Tâm", style = PemaType.body)
    }
}

@Composable
private fun A5Divider() {
    Box(Modifier.height(16.dp).fillMaxWidth(), contentAlignment = Alignment.Center) {
        HorizontalDivider(color = PemaColors.OutlineVariant)
    }
}

private fun FeatureDeps.currentProfile(session: Session): PatientProfile {
    val profiles = catalogRepository.catalog().profiles
    return profiles[session.selected.coerceIn(0, profiles.lastIndex)]
}

private fun FeatureDeps.currentPatient(
    session: Session,
    patients: Map<String, PatientState>,
): Pair<PatientProfile, PatientState> {
    val profile = currentProfile(session)
    return profile to (patients[profile.id] ?: patientsStore.of(profile.id))
}

private fun List<Order>.a5Lines(route: String): List<String> =
    flatMap { order ->
        order.items
            .filter { it.route == route }
            .map { line -> "${line.name}\n${line.quantity} ${line.unit} · ${line.usage}" }
    }

private const val unresolvedRoute = "UNRESOLVED"
private const val prescriptionRoute = "PRESCRIPTION"
private const val consultationRoute = "CONSULTATION"

private val orderRouteOptions = listOf(unresolvedRoute, prescriptionRoute, consultationRoute)
private val orderRoutesForSheets = listOf(prescriptionRoute, consultationRoute)

private fun orderRouteLabel(route: String): String =
    when (route) {
        unresolvedRoute -> "Cần phân loại"
        prescriptionRoute -> "Đơn thuốc"
        consultationRoute -> "Phiếu tư vấn"
        else -> route
    }
