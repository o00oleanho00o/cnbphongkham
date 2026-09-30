package com.pema.clinic.core.hardware

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember

@Composable actual fun rememberPlatformServices(): PlatformServices = remember { FakePlatformServices() }
