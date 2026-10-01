package com.pema.clinic.feature.patients

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
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

/**
 * Flutter `PatientSearch(onOpen:)` state: the typed query (saved, so it survives a pushed route)
 * and the profiles it matches. Render it with [patientSearchItems] inside the screen's LazyColumn.
 */
@Immutable
class PatientSearchState internal constructor(
    val query: String,
    internal val rows: List<PatientSearchRow>,
    val onQueryChange: (String) -> Unit,
    internal val onSelect: (Int) -> Unit,
)

@Composable
fun rememberPatientSearchState(deps: FeatureDeps): PatientSearchState {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val query = rememberSaveable { mutableStateOf("") }
    val catalog = deps.catalogRepository.catalog()
    return remember(deps, catalog, session, query.value) {
        PatientSearchState(
            query = query.value,
            rows = patientSearchRows(catalog, session, query.value),
            onQueryChange = { query.value = it },
            onSelect = deps.sessionStore::select,
        )
    }
}

/**
 * Flutter `PatientSearch(onOpen:)` – sample-profile picker of the Workspace tabs, as lazy items:
 * the search field, then one tile per matching profile (keyed by code). The owner sees all 46
 * profiles, so only the tiles on screen are composed.
 */
fun LazyListScope.patientSearchItems(state: PatientSearchState, onOpen: () -> Unit) {
    item(key = "patient-search-field", contentType = "patient-search-field") {
        Column {
            PemaSearchField(value = state.query, onValueChange = state.onQueryChange)
            Spacer(Modifier.height(16.dp))
        }
    }
    items(state.rows, key = { it.code }, contentType = { "patient-tile" }) { row ->
        PemaTile(
            title = row.profile.name,
            sub = "${row.code} · Đang điều trị",
            icon = "person",
            onClick = {
                state.onSelect(row.index)
                onOpen()
            },
        )
    }
}
