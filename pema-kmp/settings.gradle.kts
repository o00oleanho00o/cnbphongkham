pluginManagement {
    includeBuild("build-logic")
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "PemaKmp"
include(":androidApp")
include(":composeApp")
include(":core:common")
include(":core:ui")
include(":core:hardware")
include(":shared")
include(":feature:workspace")
include(":feature:schedule")
include(":feature:patients")
include(":feature:aftercare")
include(":feature:orders")
include(":feature:billing")
include(":feature:care")
include(":feature:finance")
