import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("com.android.kotlin.multiplatform.library")
    id("org.jetbrains.compose")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

private fun Project.defaultNamespace(): String = "com.pema.clinic" + path
    .removePrefix(":")
    .split(':')
    .joinToString(separator = "", prefix = ".") { it.replace('-', '_') }

private fun desktopTarget(): String {
    val os = System.getProperty("os.name").lowercase()
    val arm = System.getProperty("os.arch").lowercase().let { it == "aarch64" || it == "arm64" }
    return when {
        os.contains("win") -> "windows-x64"
        os.contains("mac") -> if (arm) "macos-arm64" else "macos-x64"
        else -> if (arm) "linux-arm64" else "linux-x64"
    }
}

kotlin {
    jvm {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
    }
    android {
        namespace = defaultNamespace()
        compileSdk = 37
        minSdk = 24
        withHostTest { }
        // Required so composeResources (fonts, logo, seed JSON) are packaged into the APK.
        androidResources { enable = true }
        compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
    }
    iosArm64()
    iosSimulatorArm64()

    sourceSets {
        commonMain.dependencies {
            implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
            implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
            implementation("org.jetbrains.kotlinx:kotlinx-datetime:0.7.1")
            implementation("org.jetbrains.compose.runtime:runtime:1.12.1")
            implementation("org.jetbrains.compose.ui:ui:1.12.1")
            implementation("org.jetbrains.compose.foundation:foundation:1.12.1")
            implementation("org.jetbrains.compose.material3:material3:1.9.0")
            implementation("org.jetbrains.compose.components:components-resources:1.12.1")
            implementation("org.jetbrains.androidx.navigation:navigation-compose:2.9.2")
            implementation("org.jetbrains.androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
            implementation("org.jetbrains.androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
            implementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
        }
        // Skiko native runtime so jvmTest can render screens to PNG (core:ui `renderScreen`).
        jvmTest.dependencies {
            implementation("org.jetbrains.compose.desktop:desktop-jvm-${desktopTarget()}:1.12.1")
        }
        androidMain.dependencies {
            implementation("androidx.core:core-ktx:1.17.0")
        }
    }
}

// shotVsCanvas reads the canvas references rendered by the root `canvasRefs` task.
tasks.withType<Test>().configureEach {
    if (name == "jvmTest") {
        dependsOn(":canvasRefs")
        finalizedBy(":designSpecs")
        systemProperty("pema.refDir", rootProject.layout.projectDirectory.dir("design-ref").asFile.absolutePath)
    }
}
