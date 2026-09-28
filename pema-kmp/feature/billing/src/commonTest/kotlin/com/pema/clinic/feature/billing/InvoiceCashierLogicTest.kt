package com.pema.clinic.feature.billing

import com.pema.clinic.shared.clinic.ClinicError
import com.pema.clinic.shared.clinic.ClinicStore
import com.pema.clinic.shared.clinic.pay
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class InvoiceCashierLogicTest {
    @Test
    fun invoiceMetricsAndFiltersMatchWebCashierSemantics() {
        val state = ClinicStore().state.value
        val all = buildInvoiceCashierState(state, "all")
        val due = buildInvoiceCashierState(state, "due")
        val paid = buildInvoiceCashierState(state, "paid")

        assertEquals(48, all.totalInvoices)
        assertEquals("11,3tr", all.totalDueCompact)
        assertEquals("61.650.000 ₫", all.collected)
        assertEquals(12, due.invoices.size)
        assertEquals(36, paid.invoices.size)
        assertTrue(due.invoices.all { it.due > 0 })
        assertTrue(paid.invoices.all { it.due == 0 })
    }

    @Test
    fun payingAnInvoiceUpdatesReceivedPaidAndRejectsOverCollection() {
        val store = ClinicStore()
        val row = buildInvoiceCashierState(store.state.value, "due").invoices.first()

        store.pay(row.patientId, row.invoiceId, row.due, "Tiền mặt")

        val paidRow = buildInvoiceCashierState(store.state.value, "all")
            .invoices
            .first { it.patientId == row.patientId && it.invoiceId == row.invoiceId }
        assertEquals(0, paidRow.due)
        assertTrue(paidRow.paid)
        assertFailsWith<ClinicError> { store.pay(row.patientId, row.invoiceId, 1, "Tiền mặt") }
    }
}
