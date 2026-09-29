package com.pema.clinic.shared.session

import com.pema.clinic.core.common.Routes
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import kotlin.test.Test
import kotlin.test.assertEquals

class SessionRestoreTest {
    @Test
    fun restorePutsBackSavedWorkspace() {
        val saved = Session(careMode = true, staffRole = "doctor", staffDoctor = "BS. Mai", staffName = "BS. Mai", staffSelected = 3, careSelected = 1)
        val store = SessionStore(MutableCatalogRepository())

        store.restore(saved)

        assertEquals(saved, store.state.value)
        assertEquals(true, store.state.value.allows(Routes.SendUpdate))
    }

    @Test
    fun restoreIgnoresOutOfRangePatient() {
        val store = SessionStore(MutableCatalogRepository())

        store.restore(Session(careMode = true, careSelected = 10_000))

        assertEquals(Session(), store.state.value)
    }
}
