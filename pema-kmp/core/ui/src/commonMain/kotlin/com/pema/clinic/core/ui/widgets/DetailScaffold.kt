package com.pema.clinic.core.ui.widgets

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.calculateEndPadding
import androidx.compose.foundation.layout.calculateStartPadding
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.staticCompositionLocalOf
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType

/** Back action of the current navigation entry; provided by the app shell. */
val LocalOnBack = staticCompositionLocalOf<(() -> Unit)?> { null }

/**
 * App-wide snackbar queue (Flutter `ScaffoldMessenger`). Every Pema scaffold
 * hosts it above its bottom bar, so messages show on whatever screen is on top.
 */
val LocalPemaSnackbar = staticCompositionLocalOf { SnackbarHostState() }

/**
 * Flutter `ScaffoldMessenger.of(context).showSnackBar`: posts on the app-root
 * scope, so a message survives the calling screen being popped ("save → back").
 */
class PemaMessenger(val host: SnackbarHostState, private val scope: CoroutineScope) {
    fun show(message: String) {
        scope.launch { host.showSnackbar(message) }
    }
}

/** Provided by the app shell with its root scope; null in isolated previews/tests. */
val LocalPemaMessenger = staticCompositionLocalOf<PemaMessenger?> { null }

@Composable
fun rememberPemaMessenger(): PemaMessenger {
    val root = LocalPemaMessenger.current
    val host = LocalPemaSnackbar.current
    val scope = rememberCoroutineScope()
    return root ?: remember(host, scope) { PemaMessenger(host, scope) }
}

/**
 * Flutter M3 `AppBar` under AppTheme: 64 high, paper background, ink
 * foreground, back arrow in a 48 box, title 18/600 starting at x = 72
 * (16 without leading), actions trailing. Canvas `appDetail`.
 */
@Composable
fun PemaTopBar(
    title: @Composable () -> Unit,
    modifier: Modifier = Modifier,
    onBack: (() -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {},
) {
    Row(
        modifier
            .fillMaxWidth()
            .windowInsetsPadding(pemaStatusBars)
            .height(64.dp)
            .padding(start = if (onBack != null) 4.dp else 16.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (onBack != null) {
            IconButton(onClick = onBack) { PemaIcon("arrow_back", size = 24.dp, color = PemaColors.Ink, contentDescription = "Quay lại") }
            Box(Modifier.padding(start = 20.dp).weight(1f)) { title() }
        } else {
            Box(Modifier.weight(1f)) { title() }
        }
        actions()
    }
}

/** Title text used by [PemaTopBar] in task screens (18/600 ink, one line). */
@Composable
fun PemaTopBarTitle(text: String) {
    Text(text, style = PemaType.appBarTitle, maxLines = 1, overflow = TextOverflow.Ellipsis)
}

/** Icon action for [PemaTopBar] (48dp IconButton, 24dp ink icon). */
@Composable
fun PemaTopBarAction(icon: String, onClick: () -> Unit, contentDescription: String? = null, badge: String? = null) {
    IconButton(onClick = onClick) {
        Box {
            PemaIcon(icon, size = 24.dp, color = PemaColors.Ink, contentDescription = contentDescription)
            if (badge != null) PemaBadge(badge, Modifier.align(Alignment.TopStart).padding(start = 14.dp).padding(top = 0.dp))
        }
    }
}

/**
 * Flutter `DetailScaffold`: titled app bar, SafeArea, 720 max width, content
 * padded 20 (canvas `appDetail` screens). Content is a scrolling Column – put
 * the same children as the Flutter `ListView(children: [...])`.
 */
@Composable
fun DetailScaffold(
    title: String,
    modifier: Modifier = Modifier,
    onBack: (() -> Unit)? = LocalOnBack.current,
    actions: @Composable RowScope.() -> Unit = {},
    floatingActionButton: @Composable () -> Unit = {},
    bottomBar: @Composable () -> Unit = {},
    contentPadding: PaddingValues = PaddingValues(20.dp),
    content: @Composable ColumnScope.() -> Unit,
) {
    PemaScaffold(
        modifier = modifier,
        topBar = { PemaTopBar(title = { PemaTopBarTitle(title) }, onBack = onBack, actions = actions) },
        floatingActionButton = floatingActionButton,
        bottomBar = bottomBar,
    ) { inner ->
        Box(Modifier.fillMaxSize().padding(inner), contentAlignment = Alignment.TopCenter) {
            Column(
                Modifier
                    .widthIn(max = 720.dp)
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .windowInsetsPadding(pemaNavigationBars.only(WindowInsetsSides.Bottom))
                    .padding(contentPadding),
                content = content,
            )
        }
    }
}

/** [DetailScaffold] with a lazy list body, for long lists (patients, procedures…). */
@Composable
fun LazyDetailScaffold(
    title: String,
    modifier: Modifier = Modifier,
    onBack: (() -> Unit)? = LocalOnBack.current,
    actions: @Composable RowScope.() -> Unit = {},
    floatingActionButton: @Composable () -> Unit = {},
    state: LazyListState = rememberLazyListState(),
    contentPadding: PaddingValues = PaddingValues(20.dp),
    content: LazyListScope.() -> Unit,
) {
    PemaScaffold(
        modifier = modifier,
        topBar = { PemaTopBar(title = { PemaTopBarTitle(title) }, onBack = onBack, actions = actions) },
        floatingActionButton = floatingActionButton,
    ) { inner ->
        Box(Modifier.fillMaxSize().padding(inner), contentAlignment = Alignment.TopCenter) {
            LazyColumn(
                Modifier.widthIn(max = 720.dp).fillMaxSize().windowInsetsPadding(pemaNavigationBars.only(WindowInsetsSides.Bottom)),
                state = state,
                contentPadding = contentPadding,
                content = content,
            )
        }
    }
}

/**
 * M3 Scaffold on paper with the shared snackbar host (Flutter `Scaffold`).
 * Insets are handled by the bars/content, not by the Scaffold – except the
 * keyboard: like Flutter `resizeToAvoidBottomInset`, the body's bottom padding
 * becomes max(bottom bar, IME) and the snackbar sits above the keyboard.
 */
@Composable
fun PemaScaffold(
    modifier: Modifier = Modifier,
    topBar: @Composable () -> Unit = {},
    bottomBar: @Composable () -> Unit = {},
    floatingActionButton: @Composable () -> Unit = {},
    content: @Composable (PaddingValues) -> Unit,
) {
    val snackbar = LocalPemaSnackbar.current
    Scaffold(
        modifier = modifier,
        topBar = topBar,
        bottomBar = bottomBar,
        floatingActionButton = floatingActionButton,
        snackbarHost = {
            SnackbarHost(snackbar, Modifier.windowInsetsPadding(WindowInsets.ime)) { PemaSnackbar(it) }
        },
        containerColor = PemaColors.Paper,
        contentColor = PemaColors.Ink,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
    ) { inner ->
        val ime = WindowInsets.ime.asPaddingValues().calculateBottomPadding()
        val direction = LocalLayoutDirection.current
        content(
            if (ime <= inner.calculateBottomPadding()) {
                inner
            } else {
                PaddingValues(
                    start = inner.calculateStartPadding(direction),
                    top = inner.calculateTopPadding(),
                    end = inner.calculateEndPadding(direction),
                    bottom = ime,
                )
            },
        )
    }
}

/** Vertical spacer helper (canvas `sp`). */
@Composable
fun ColumnScope.Gap(height: Int) {
    androidx.compose.foundation.layout.Spacer(Modifier.height(height.dp))
}

