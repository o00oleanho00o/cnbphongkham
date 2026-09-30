package com.pema.clinic.feature.care

import com.pema.clinic.shared.care.CareQueueFilter
import com.pema.clinic.shared.care.careNotContacted
import com.pema.clinic.shared.care.CareQueue as SharedCareQueue
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import com.pema.clinic.shared.catalog.sampleCatalog
import com.pema.clinic.shared.patients.PatientsStore
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals

@OptIn(ExperimentalCoroutinesApi::class)
class CareQueueLogicTest {
    @Test
    fun careQueueTracksContactStatusButIgnoresCartEdits() = runTest {
        val catalog = MutableCatalogRepository(sampleCatalog())
        val patients = PatientsStore(catalog)
        val care = SharedCareQueue(catalog, patients, backgroundScope)
        runCurrent()

        val first = care.cases().first()
        assertEquals(careNotContacted, first.status)
        var notified = 0
        backgroundScope.launch { care.state.drop(1).collect { notified++ } }
        runCurrent()

        patients.addToCart(first.profile.id, catalog.catalog().products.first())
        runCurrent()
        assertEquals(0, notified)

        patients.update(first.profile.id) { it.copy(careStatus = "Đã liên hệ") }
        runCurrent()
        assertEquals("Đã liên hệ", care.statusOf(first.profile.id))
        assertEquals(1, notified)
    }

    @Test
    fun groupBucketAndSearchFiltersMatchFlutterCareCases() = runTest {
        val catalog = MutableCatalogRepository(sampleCatalog())
        val patients = PatientsStore(catalog)
        val care = SharedCareQueue(catalog, patients, backgroundScope)
        runCurrent()

        assertEquals(10, care.cases().size)
        assertEquals(10, care.rows(CareQueueFilter()).size)
        assertEquals("10 khách", care.rowCountLabel(10))
        assertEquals("Danh sách cần chăm sóc", care.titleForBucket(careNotContacted))
        assertEquals(listOf("Trần Minh Châu"), care.rows(CareQueueFilter(group = "d3")).map { it.name })
        assertEquals(listOf("Trần Minh Châu"), care.rows(CareQueueFilter(query = "trần")).map { it.name })

        patients.update("P038") { it.copy(careStatus = "Đã liên hệ") }
        runCurrent()
        assertEquals(listOf("Trần Minh Châu"), care.rows(CareQueueFilter(bucket = "Đã liên hệ")).map { it.name })
        assertEquals(emptyList(), care.rows(CareQueueFilter(group = "d3")))
    }
}
