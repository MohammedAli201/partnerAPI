plugins { id("com.android.library") }
android {
 namespace="no.jubapay.payoutworker.device"; compileSdk=37
 defaultConfig { minSdk=24 }
 compileOptions { sourceCompatibility=JavaVersion.VERSION_11; targetCompatibility=JavaVersion.VERSION_11 }
}
dependencies { implementation(project(":domain")); implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2") }
