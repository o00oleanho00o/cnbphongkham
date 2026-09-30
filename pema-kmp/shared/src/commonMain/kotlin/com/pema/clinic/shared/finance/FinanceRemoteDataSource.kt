package com.pema.clinic.shared.finance

import com.pema.clinic.core.common.ApiConfig
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** HTTP access to `prototype/finance_server.py`. */
class FinanceRemoteDataSource(
    private val client: HttpClient,
    val baseUrl: String = ApiConfig.DEFAULT_FINANCE_API,
) {
    private val json = Json { ignoreUnknownKeys = true }

    private fun io.ktor.client.request.HttpRequestBuilder.pemaHeaders(role: String, doctor: String) {
        header("Content-Type", "application/json")
        header("X-Pema-Role", role)
        header("X-Pema-Doctor", doctor)
    }

    suspend fun fetchState(month: String, role: String, doctor: String): JsonObject {
        val response = withTimeout(7_000) {
            client.get("$baseUrl/state") {
                parameter("month", month)
                pemaHeaders(role, doctor)
            }
        }
        val value = json.parseToJsonElement(response.bodyAsText().ifBlank { "{}" }).jsonObject
        if (response.status.value != 200) throw Exception(value["error"]?.jsonPrimitive?.content)
        return value
    }

    suspend fun postCommand(action: String, body: Map<String, Any?>, role: String, doctor: String) {
        val response = withTimeout(8_000) {
            client.post("$baseUrl/command/$action") {
                pemaHeaders(role, doctor)
                contentType(ContentType.Application.Json)
                setBody(toJson(body))
            }
        }
        if (response.status.value != 200) {
            val value = json.parseToJsonElement(response.bodyAsText().ifBlank { "{}" }).jsonObject
            throw Exception(value["error"]?.jsonPrimitive?.content)
        }
    }

    private fun toJson(value: Any?): String = when (value) {
        null -> "null"
        is String -> JsonPrimitive(value).toString()
        is Number, is Boolean -> value.toString()
        is Map<*, *> -> value.entries.joinToString(prefix = "{", postfix = "}") { (key, item) ->
            toJson(key.toString()) + ":" + toJson(item)
        }
        is Iterable<*> -> value.joinToString(prefix = "[", postfix = "]") { toJson(it) }
        else -> toJson(value.toString())
    }
}
