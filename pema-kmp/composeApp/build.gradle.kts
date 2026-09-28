plugins { id("pema.kmp.library") }


kotlin {
    sourceSets {
        commonMain.dependencies {
            implementation(project(":core:common"))
            implementation(project(":core:hardware"))
            implementation(project(":core:ui"))
            implementation(project(":shared"))
            implementation(project(":feature:workspace"))
            implementation(project(":feature:schedule"))
            implementation(project(":feature:patients"))
            implementation(project(":feature:aftercare"))
            implementation(project(":feature:orders"))
            implementation(project(":feature:billing"))
            implementation(project(":feature:care"))
            implementation(project(":feature:finance"))
        }
    }
}
