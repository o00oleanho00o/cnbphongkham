plugins { id("pema.kmp.library") }


kotlin {
    sourceSets {
        commonMain.dependencies {
            implementation(project(":core:common"))
            implementation(project(":core:hardware"))
            implementation(project(":core:ui"))
            implementation(project(":shared"))
            // Workspace tabs embed CareQueue (care) and PatientSearch (patients).
            implementation(project(":feature:care"))
            implementation(project(":feature:patients"))
        }
    }
}
