plugins { `kotlin-dsl` }

group = "com.pema.clinic.buildlogic"

dependencies {
    implementation("org.jetbrains.kotlin:kotlin-gradle-plugin:2.4.0")
    implementation("org.jetbrains.kotlin:compose-compiler-gradle-plugin:2.4.0")
    implementation("org.jetbrains.kotlin:kotlin-serialization:2.4.0")
    implementation("com.android.tools.build:gradle:9.1.0")
    implementation("org.jetbrains.compose:compose-gradle-plugin:1.12.1")
}