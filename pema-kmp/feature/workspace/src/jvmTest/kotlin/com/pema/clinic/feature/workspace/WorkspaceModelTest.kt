package com.pema.clinic.feature.workspace

import com.pema.clinic.core.common.Routes
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import com.pema.clinic.shared.catalog.sampleCatalog
import com.pema.clinic.shared.patients.PatientState
import com.pema.clinic.shared.patients.PatientsStore
import com.pema.clinic.shared.session.Session
import com.pema.clinic.shared.session.SessionStore
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class WorkspaceModelTest {
    @Test
    fun mobileRoleWorkspaceRulesAndPatientIsolationMatchFlutter() {
        val catalogRepository = MutableCatalogRepository(sampleCatalog())
        val catalog = catalogRepository.catalog()
        val session = SessionStore(catalogRepository)
        val patients = PatientsStore(catalogRepository)

        assertEquals(46, catalog.profiles.size)
        val cases = catalog.profiles.filter { it.inCareQueue }
        assertEquals(10, cases.map { it.careGroup }.toSet().size)
        cases.forEach { assertTrue(it.hasTask(it.careGroup), it.id) }

        session.select(36)
        val id = session.selectedPatientId()
        patients.update(id) {
            it.copy(
                note = "Clinical",
                response = "Approved reply",
                day = "2026-10-01",
                appointment = "14:00",
                acknowledged = true,
                updates = listOf("My update"),
                careNote = "PRIVATE",
                escalations = listOf("Internal"),
                editingOrder = "Draft",
            )
        }
        patients.addToCart(id, catalog.products.first())

        session.select(37)
        fun current(): PatientState = patients.of(session.selectedPatientId())
        assertEquals("", current().note)
        assertEquals("", current().response)
        assertEquals("", current().day)
        assertFalse(current().acknowledged)
        assertTrue(current().updates.isEmpty())
        assertTrue(current().cart.isEmpty())
        assertNull(current().editingOrder)
        assertEquals("", current().careNote)
        assertTrue(current().escalations.isEmpty())

        session.select(36)
        assertEquals("Clinical", current().note)
        assertEquals("2026-10-01", current().day)
        assertEquals(1, current().cart.size)
        session.enterCare()
        assertEquals(0, session.state.value.selected)
        session.select(38)
        session.enterStaff("owner", "BS. Tâm")
        assertEquals(36, session.state.value.selected)

        val care = Session(staffRole = "care")
        assertFalse(care.allows(Routes.Consultation))
        assertFalse(care.allows("Thu ngân"))
        assertTrue(care.allows("Chăm sóc khách hàng"))
        assertTrue(care.allows(Routes.Booking))
        assertFalse(care.allows(Routes.Patient360))

        val accountant = Session(staffRole = "accountant")
        assertTrue(accountant.allows(Routes.Cashier))
        assertTrue(accountant.allows(Routes.Invoices))
        assertTrue(accountant.allows(Routes.Guide))
        assertFalse(accountant.allows(Routes.Finance))

        val mai = Session(staffRole = "doctor", staffDoctor = "BS. Mai")
        assertFalse(mai.owns(catalog.profiles[36]))
        assertTrue(mai.owns(catalog.profiles[37]))
        assertFalse(mai.billing)
        assertFalse(mai.allows(Routes.Cashier))
        assertFalse(mai.allows(Routes.Resources))
        assertFalse(mai.allows(Routes.Services))
        assertFalse(mai.allows(Routes.CustomerCare))
        assertTrue(mai.allows(Routes.QuickOrder))
    }
}
