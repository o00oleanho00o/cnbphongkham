package com.pema.clinic

import com.pema.clinic.core.common.ApiConfig
import com.pema.clinic.core.common.AppNavigator
import com.pema.clinic.core.common.createHttpClient
import com.pema.clinic.core.hardware.PlatformServices
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.billing.ReceiptsStore
import com.pema.clinic.shared.care.CareQueue
import com.pema.clinic.shared.care.ReviewQueue
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import com.pema.clinic.shared.finance.FinanceRemoteDataSource
import com.pema.clinic.shared.finance.FinanceRepositoryImpl
import com.pema.clinic.shared.finance.FinanceStore
import com.pema.clinic.shared.orders.OrdersStore
import com.pema.clinic.shared.patients.PatientsStore
import com.pema.clinic.shared.session.SessionStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class AppContainer(
    navigator: AppNavigator,
    platform: PlatformServices,
    financeApi: String = ApiConfig.DEFAULT_FINANCE_API,
    scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default),
) {
    val catalogRepository = MutableCatalogRepository()
    val sessionStore = SessionStore(catalogRepository)
    val patientsStore = PatientsStore(catalogRepository)
    val ordersStore = OrdersStore(patientsStore, catalogRepository)
    val receiptsStore = ReceiptsStore(sessionStore, ordersStore)
    val careQueue = CareQueue(catalogRepository, patientsStore, scope)
    val reviewQueue = ReviewQueue(catalogRepository, patientsStore, sessionStore, scope)
    val financeRepository = FinanceRepositoryImpl(FinanceRemoteDataSource(createHttpClient(), financeApi))
    val financeStore = FinanceStore(financeRepository, scope)

    val deps = FeatureDeps(
        navigator = navigator,
        platform = platform,
        catalogRepository = catalogRepository,
        sessionStore = sessionStore,
        patientsStore = patientsStore,
        ordersStore = ordersStore,
        receiptsStore = receiptsStore,
        careQueue = careQueue,
        reviewQueue = reviewQueue,
        financeStore = financeStore,
    )
}
