package com.pema.clinic.feature.patients

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pema.clinic.core.ui.widgets.PemaSearchField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.catalog.Catalog
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.session.Session

internal data class PatientSearchRow(
    val index: Int,
    val code: String,
    val profile: PatientProfile,
)

internal fun patientCodeForIndex(index: Int): String = "P${(index + 1).toString().padStart(3, '0')}"

internal fun patientSearchRows(catalog: Catalog, session: Session, query: String): List<PatientSearchRow> {
    val lower = query.lowercase()
    return catalog.profiles.mapIndexedNotNull { index, profile ->
        val code = patientCodeForIndex(index)
        if (session.owns(profile) && (profile.matches(lower) || code.lowercase().contains(lower))) {
            PatientSearchRow(index = index, code = code, profile = profile)
        } else {
            null
        }
    }
}

/** Flutter `PatientSearch(onOpen:)` – sample-profile picker used by Workspace tabs. */
@Composable
fun PatientSearch(deps: FeatureDeps, onOpen: () -> Unit, modifier: Modifier = Modifier) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    var query by rememberSaveable { mutableStateOf("") }
    val catalog = deps.catalogRepository.catalog()
    val rows = patientSearchRows(catalog, session, query)

    Column(modifier) {
        PemaSearchField(value = query, onValueChange = { query = it })
        Spacer(Modifier.height(16.dp))
        rows.forEach { row ->
            PemaTile(
                title = row.profile.name,
                sub = "${row.code} · Đang điều trị",
                icon = "person",
                onClick = {
                    deps.sessionStore.select(row.index)
                    onOpen()
                },
            )
        }
    }
}
