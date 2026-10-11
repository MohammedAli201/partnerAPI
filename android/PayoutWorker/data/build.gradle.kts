plugins {
 id("com.android.library")
 id("com.google.devtools.ksp") version "2.3.12"
}
android {
 namespace="no.jubapay.payoutworker.data"
 compileSdk=37
 defaultConfig { minSdk=24; testInstrumentationRunner="androidx.test.runner.AndroidJUnitRunner" }
 compileOptions { sourceCompatibility=JavaVersion.VERSION_11; targetCompatibility=JavaVersion.VERSION_11 }
}
ksp { arg("room.schemaLocation", "$projectDir/schemas") }
dependencies {
 implementation(project(":domain"))
 implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
 implementation("androidx.room:room-runtime:2.8.5")
 implementation("androidx.room:room-ktx:2.8.5")
 ksp("androidx.room:room-compiler:2.8.5")
 implementation("com.squareup.okhttp3:okhttp:5.3.2")
 androidTestImplementation("androidx.test.ext:junit:1.2.1")
 androidTestImplementation("androidx.test:runner:1.6.2")
 androidTestImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
}
