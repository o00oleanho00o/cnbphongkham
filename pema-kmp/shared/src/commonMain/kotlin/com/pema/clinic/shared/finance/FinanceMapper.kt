package com.pema.clinic.shared.finance

import com.pema.clinic.shared.catalog.int
import com.pema.clinic.shared.catalog.string
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** Converts the finance API JSON to domain models and back. */
object FinanceMapper {
    private val json = Json { ignoreUnknownKeys = true }

    fun snapshot(text: String): FinanceSnapshot = snapshot(json.parseToJsonElement(text).jsonObject)

    fun snapshot(json: JsonObject): FinanceSnapshot {
        val summary = json.getValue("summary").jsonObject
        return FinanceSnapshot(
            month = json.string("month"),
            today = json.string("today"),
            periodStatus = json.getValue("period").jsonObject.string("status"),
            summary = FinanceSummary(
                revenue = summary.int("revenue"),
                fee = summary.int("fee"),
                pending = summary.int("pending"),
                collected = summary.optionalInt("collected"),
                debt = summary.optionalInt("debt"),
            ),
            doctors = json.objects("doctors").map { FinanceDoctor(id = it.string("id"), name = it.string("name")) },
            services = json.objects("services").map {
                ProcedureService(
                    id = it.string("id"),
                    name = it.string("name"),
                    price = it.int("price"),
                    rate = it.int("rate"),
                    basis = it.string("basis"),
                    version = it.int("version"),
                )
            },
            rows = json.objects("rows").map {
                ProcedureRow(
                    id = it.string("id"),
                    date = it.string("date"),
                    patient = it.string("patient"),
                    service = it.string("service"),
                    doctor = it.string("doctor"),
                    status = it.string("status"),
                    base = it.int("base"),
                    rate = it.int("rate"),
                    revenue = it.int("revenue"),
                    fee = it.int("fee"),
                )
            },
            invoices = json.objects("invoices").map {
                FinanceInvoice(
                    id = it.string("id"),
                    patient = it.string("patient"),
                    source = it.string("source"),
                    amount = it.int("amount"),
                    received = it.int("received"),
                )
            },
            notifications = json.objects("notifications").map {
                PaymentNotification(
                    id = it.string("id"),
                    title = it.string("title"),
                    body = it.string("body"),
                    read = it.getValue("read").jsonPrimitive.boolean,
                    at = it.string("at"),
                )
            },
        )
    }

    fun entry(entry: ProcedureEntry): Map<String, Any?> = mapOf(
        "patient" to entry.patient,
        "invoice" to entry.invoice,
        "service" to entry.service,
        "date" to entry.date,
        "list" to entry.listPrice,
        "discount" to entry.discount,
        "note" to entry.note,
        "people" to entry.people.map { mapOf("doctor" to it.doctor, "share" to it.share, "rate" to it.rate) },
    )
}

private fun JsonObject.optionalInt(name: String): Int? = get(name)?.jsonPrimitive?.int
private fun JsonObject.objects(name: String): List<JsonObject> = get(name)?.jsonArray?.map { it.jsonObject }.orEmpty()
