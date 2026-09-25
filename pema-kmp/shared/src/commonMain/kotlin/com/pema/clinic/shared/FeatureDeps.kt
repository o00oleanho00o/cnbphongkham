package com.pema.clinic.shared

import com.pema.clinic.core.common.AppNavigator
import com.pema.clinic.core.hardware.PlatformServices
import com.pema.clinic.shared.billing.ReceiptsStore
import com.pema.clinic.shared.care.CareQueue
import com.pema.clinic.shared.care.ReviewQueue
import com.pema.clinic.shared.catalog.CatalogRepository
import com.pema.clinic.shared.finance.FinanceStore
import com.pema.clinic.shared.orders.OrdersStore
import com.pema.clinic.shared.patients.PatientsStore
import com.pema.clinic.shared.session.SessionStore

/** App-scoped dependencies shared by feature modules. */
data class FeatureDeps(
    /** Push/back navigation abstraction used by features instead of owning a NavController. */
    val navigator: AppNavigator,
    /** Platform services such as camera/photo capture. */
    val platform: PlatformServices,
    /** Read-only bundled products and patient profiles. */
    val catalogRepository: CatalogRepository,
    /** Workspace/session role and selected patient state. */
    val sessionStore: SessionStore,
    /** Per-patient session-only clinical, care, photo and cart state. */
    val patientsStore: PatientsStore,
    /** Draft/approved orders saved from patient carts. */
    val ordersStore: OrdersStore,
    /** Demo receipt totals and derived current bills. */
    val receiptsStore: ReceiptsStore,
    /** CSKH queue cases and pure filter/bucket helpers. */
    val careQueue: CareQueue,
    /** Doctor review queue for D+7, patient updates and CSKH escalations. */
    val reviewQueue: ReviewQueue,
    /** App-scoped finance projection, polling and command state. */
    val financeStore: FinanceStore,
)
