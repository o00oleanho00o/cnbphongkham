plugins { id("pema.kmp.library") }

kotlin {
    sourceSets {
        commonMain.dependencies {
            implementation(project(":core:common"))
            api(project(":core:hardware"))
        }
    }
}

compose.resources {
    publicResClass = true
    packageOfResClass = "com.pema.clinic.core.ui.generated.resources"
    generateResClass = always
}
