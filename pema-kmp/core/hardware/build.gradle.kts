plugins { id("pema.kmp.library") }

kotlin {
    android {
        // FileProvider paths (res/xml/pema_file_paths.xml) must be merged into the app.
        androidResources { enable = true }
    }
    sourceSets {
        androidMain.dependencies {
            implementation(libs.androidx.activity.compose)
            implementation(libs.androidx.core.ktx)
            implementation(libs.androidx.exifinterface)
        }
    }
}